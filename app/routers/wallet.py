from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import uuid
import hmac
import hashlib
import json
from typing import Optional
from datetime import datetime, timezone

from app.database import get_db
from app.models import Transaction, TransactionStatus, User, Wallet, Transfer
from app.schemas import (
    PaymentInitiateRequest,
    PaymentInitiateResponse,
    TransactionStatusResponse,
    WebhookResponse,
    WalletBalanceResponse,
    WalletTransferRequest,
    WalletTransferResponse,
    TransactionHistoryItem
)
from app.config import settings
from app.auth_utils import require_permission

router = APIRouter(prefix="/wallet", tags=["Wallet"])

# Paystack API URLs
PAYSTACK_INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"


@router.post("/deposit", response_model=PaymentInitiateResponse, status_code=status.HTTP_201_CREATED)
async def wallet_deposit(
    payment_request: PaymentInitiateRequest,
    current_user: User = Depends(require_permission("deposit")),
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate a wallet deposit via Paystack.
    
    Authentication:
    - JWT: Send Bearer token in Authorization header
    - API Key: Send API key in X-API-Key header (requires 'deposit' permission)
    
    The email is automatically taken from the authenticated user.
    Amount is in kobo (smallest currency unit).
    
    Returns payment reference and authorization URL for user to complete payment.
    """
    try:
        # Validate amount
        if payment_request.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be greater than 0"
            )
        
        # Generate unique reference
        reference = f"txn_{uuid.uuid4().hex}"
        
        # Check if reference already exists (idempotency)
        result = await db.execute(select(Transaction).where(Transaction.reference == reference))
        existing_transaction = result.scalar_one_or_none()
        
        if existing_transaction:
            return PaymentInitiateResponse(
                reference=existing_transaction.reference,
                authorization_url=existing_transaction.authorization_url
            )
        
        # Call Paystack Initialize Transaction API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                PAYSTACK_INITIALIZE_URL,
                headers={
                    "Authorization": f"Bearer {settings.paystack_secret_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "amount": payment_request.amount,
                    "email": current_user.email,  # Email from authenticated user
                    "reference": reference,
                    "currency": "NGN"
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"Payment initiation failed: {response.text}"
                )
            
            paystack_data = response.json()
            
            if not paystack_data.get("status"):
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Payment initiation failed by Paystack"
                )
            
            authorization_url = paystack_data["data"]["authorization_url"]
            
            # Persist transaction in database
            transaction = Transaction(
                reference=reference,
                user_id=current_user.id,
                amount=payment_request.amount,
                status=TransactionStatus.PENDING,
                authorization_url=authorization_url
            )
            db.add(transaction)
            await db.commit()
            await db.refresh(transaction)
            
            return PaymentInitiateResponse(
                reference=transaction.reference,
                authorization_url=transaction.authorization_url
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/paystack/webhook", response_model=WebhookResponse)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_paystack_signature: Optional[str] = Header(None)
):
    """
    Webhook endpoint to receive transaction updates from Paystack.
    
    Security: Validates Paystack signature
    Actions:
    - Verify signature
    - Find transaction by reference
    - Update transaction status
    - Credit wallet balance on success
    
    ⚠️ Only this endpoint is allowed to credit wallets.
    """
    try:
        # Get request body
        body = await request.body()
        
        # Verify Paystack signature
        if not x_paystack_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Paystack signature"
            )
        
        # Compute expected signature
        computed_signature = hmac.new(
            settings.paystack_webhook_secret.encode('utf-8'),
            body,
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(computed_signature, x_paystack_signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature"
            )
        
        # Parse event payload
        event = json.loads(body)
        
        event_type = event.get("event")
        data = event.get("data", {})
        
        # Handle successful charges
        if event_type == "charge.success":
            reference = data.get("reference")
            
            if reference:
                # Find transaction in database
                result = await db.execute(select(Transaction).where(Transaction.reference == reference))
                transaction = result.scalar_one_or_none()
                
                if transaction and transaction.status == TransactionStatus.PENDING:
                    # Update transaction status
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.paid_at = datetime.now(timezone.utc)
                    
                    # Credit wallet (create wallet if doesn't exist)
                    wallet_result = await db.execute(
                        select(Wallet).where(Wallet.user_id == transaction.user_id)
                    )
                    wallet = wallet_result.scalar_one_or_none()
                    
                    if not wallet:
                        # Create wallet for user
                        wallet = Wallet(
                            id=str(uuid.uuid4()),
                            user_id=transaction.user_id,
                            balance=0
                        )
                        db.add(wallet)
                    
                    # Credit wallet balance
                    wallet.balance += transaction.amount
                    
                    await db.commit()
        
        # Note: Paystack doesn't send webhooks for declined/failed transactions
        # Failed transactions remain as "pending" in the database
        # Use the status endpoint to check if needed
        
        return WebhookResponse(status=True)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {str(e)}"
        )


@router.get("/deposit/{reference}/status", response_model=TransactionStatusResponse)
async def get_deposit_status(
    reference: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check deposit transaction status by reference.
    
    ⚠️ This endpoint does NOT credit wallets.
    Only the webhook is allowed to credit wallets.
    
    Returns current transaction status from database.
    """
    try:
        # Find transaction in database
        result = await db.execute(select(Transaction).where(Transaction.reference == reference))
        transaction = result.scalar_one_or_none()
        
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        return TransactionStatusResponse(
            reference=transaction.reference,
            status=transaction.status.value,
            amount=transaction.amount,
            paid_at=transaction.paid_at
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    current_user: User = Depends(require_permission("read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Get wallet balance for authenticated user.
    
    Authentication:
    - JWT: Send Bearer token in Authorization header
    - API Key: Send API key in X-API-Key header (requires 'read' permission)
    
    Returns balance in kobo.
    """
    try:
        # Get user's wallet
        result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
        wallet = result.scalar_one_or_none()
        
        if not wallet:
            # Create wallet if doesn't exist
            wallet = Wallet(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                balance=0
            )
            db.add(wallet)
            await db.commit()
            await db.refresh(wallet)
        
        return WalletBalanceResponse(balance=wallet.balance)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/transfer", response_model=WalletTransferResponse)
async def wallet_transfer(
    transfer_request: WalletTransferRequest,
    current_user: User = Depends(require_permission("transfer")),
    db: AsyncSession = Depends(get_db)
):
    """
    Transfer funds from your wallet to another user's wallet.
    
    Authentication:
    - JWT: Send Bearer token in Authorization header
    - API Key: Send API key in X-API-Key header (requires 'transfer' permission)
    
    Rules:
    - Cannot transfer to yourself
    - Must have sufficient balance
    - Amount is in kobo
    """
    try:
        # Validate not transferring to self
        if transfer_request.wallet_number == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot transfer to your own wallet"
            )
        
        # Get sender's wallet
        sender_result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
        sender_wallet = sender_result.scalar_one_or_none()
        
        if not sender_wallet:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sender wallet not found. Please deposit first."
            )
        
        # Check sufficient balance
        if sender_wallet.balance < transfer_request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient balance. Available: {sender_wallet.balance} kobo"
            )
        
        # Get recipient's wallet (wallet_number is the user_id)
        recipient_result = await db.execute(
            select(Wallet).where(Wallet.user_id == transfer_request.wallet_number)
        )
        recipient_wallet = recipient_result.scalar_one_or_none()
        
        if not recipient_wallet:
            # Check if recipient user exists
            user_result = await db.execute(
                select(User).where(User.id == transfer_request.wallet_number)
            )
            recipient_user = user_result.scalar_one_or_none()
            
            if not recipient_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Recipient wallet not found"
                )
            
            # Create wallet for recipient
            recipient_wallet = Wallet(
                id=str(uuid.uuid4()),
                user_id=recipient_user.id,
                balance=0
            )
            db.add(recipient_wallet)
        
        # Perform transfer
        sender_wallet.balance -= transfer_request.amount
        recipient_wallet.balance += transfer_request.amount
        
        # Record transfer
        transfer = Transfer(
            id=str(uuid.uuid4()),
            sender_id=current_user.id,
            recipient_id=transfer_request.wallet_number,
            amount=transfer_request.amount,
            status=TransactionStatus.SUCCESS
        )
        db.add(transfer)
        
        await db.commit()
        
        return WalletTransferResponse(
            status="success",
            message=f"Transfer of {transfer_request.amount} kobo completed successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/transactions", response_model=list[TransactionHistoryItem])
async def get_transaction_history(
    current_user: User = Depends(require_permission("read")),
    db: AsyncSession = Depends(get_db)
):
    """
    Get transaction history for authenticated user.
    
    Authentication:
    - JWT: Send Bearer token in Authorization header
    - API Key: Send API key in X-API-Key header (requires 'read' permission)
    
    Returns list of deposits and transfers.
    """
    try:
        history = []
        
        # Get deposits (successful transactions)
        deposits_result = await db.execute(
            select(Transaction).where(
                Transaction.user_id == current_user.id,
                Transaction.status == TransactionStatus.SUCCESS
            ).order_by(Transaction.created_at.desc())
        )
        deposits = deposits_result.scalars().all()
        
        for deposit in deposits:
            history.append(TransactionHistoryItem(
                type="deposit",
                amount=deposit.amount,
                status=deposit.status.value,
                timestamp=deposit.paid_at or deposit.created_at
            ))
        
        # Get sent transfers
        sent_transfers_result = await db.execute(
            select(Transfer).where(
                Transfer.sender_id == current_user.id
            ).order_by(Transfer.created_at.desc())
        )
        sent_transfers = sent_transfers_result.scalars().all()
        
        for transfer in sent_transfers:
            history.append(TransactionHistoryItem(
                type="transfer",
                amount=transfer.amount,
                status=transfer.status.value,
                timestamp=transfer.created_at
            ))
        
        # Sort by timestamp descending
        history.sort(key=lambda x: x.timestamp, reverse=True)
        
        return history
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


