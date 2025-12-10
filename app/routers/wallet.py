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
from app.models import Transaction, TransactionStatus, User, Wallet
from app.schemas import (
    PaymentInitiateRequest,
    PaymentInitiateResponse,
    TransactionStatusResponse,
    WebhookResponse
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
        
        elif event_type == "charge.failed":
            reference = data.get("reference")
            
            if reference:
                result = await db.execute(select(Transaction).where(Transaction.reference == reference))
                transaction = result.scalar_one_or_none()
                
                if transaction and transaction.status == TransactionStatus.PENDING:
                    transaction.status = TransactionStatus.FAILED
                    await db.commit()
        
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
