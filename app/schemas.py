from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


# Google Auth Schemas
class GoogleAuthURLResponse(BaseModel):
    google_auth_url: str


class GoogleCallbackResponse(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    access_token: str
    token_type: str = "bearer"


# Paystack Payment Schemas
class PaymentInitiateRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in kobo (lowest currency unit)")
    
    @field_validator('amount', mode='before')
    @classmethod
    def convert_to_kobo(cls, v):
        """
        Accepts both integers (kobo) and floats (naira).
        If float is provided, converts to kobo automatically.
        
        Examples:
        - 5000 → 5000 kobo (50 NGN)
        - 50.75 → 5075 kobo (50.75 NGN)
        """
        if isinstance(v, float):
            # Convert naira to kobo (multiply by 100 and round)
            return int(round(v * 100))
        return v


class PaymentInitiateResponse(BaseModel):
    reference: str
    authorization_url: str


class TransactionStatusResponse(BaseModel):
    reference: str
    status: str
    amount: int
    paid_at: Optional[datetime] = None


class WebhookResponse(BaseModel):
    status: bool


# API Key Schemas
class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")
    permissions: List[str] = Field(..., min_items=1, description="List of permissions: deposit, transfer, read")
    expiry: str = Field(..., pattern="^(1H|1D|1M|1Y)$", description="Expiry duration: 1H, 1D, 1M, 1Y")
    
    @field_validator('permissions')
    @classmethod
    def validate_permissions(cls, v):
        allowed_permissions = {"deposit", "transfer", "read"}
        invalid = set(v) - allowed_permissions
        if invalid:
            raise ValueError(f"Invalid permissions: {invalid}. Allowed: {allowed_permissions}")
        return v


class APIKeyCreateResponse(BaseModel):
    api_key: str
    expires_at: datetime


class APIKeyRolloverRequest(BaseModel):
    expired_key_id: str = Field(..., description="ID of the expired API key")
    expiry: str = Field(..., pattern="^(1H|1D|1M|1Y)$", description="Expiry duration: 1H, 1D, 1M, 1Y")


class APIKeyRolloverResponse(BaseModel):
    api_key: str
    expires_at: datetime


# Wallet Schemas
class WalletBalanceResponse(BaseModel):
    balance: int = Field(..., description="Wallet balance in kobo")


class WalletTransferRequest(BaseModel):
    wallet_number: str = Field(..., description="Recipient's wallet number (user_id)")
    amount: int = Field(..., gt=0, description="Amount to transfer in kobo")


class WalletTransferResponse(BaseModel):
    status: str
    message: str


class TransactionHistoryItem(BaseModel):
    type: str = Field(..., description="Transaction type: deposit or transfer")
    amount: int = Field(..., description="Amount in kobo")
    status: str = Field(..., description="Transaction status: success, pending, failed")
    timestamp: datetime = Field(..., description="Transaction timestamp")


