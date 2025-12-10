from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
import secrets
import hashlib
import uuid

from app.database import get_db
from app.models import APIKey, User
from app.schemas import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyRolloverRequest,
    APIKeyRolloverResponse
)
from app.auth_utils import get_current_user

router = APIRouter(prefix="/keys", tags=["API Keys"])


def parse_expiry(expiry: str) -> datetime:
    """
    Convert expiry string (1H, 1D, 1M, 1Y) to datetime.
    """
    now = datetime.now(timezone.utc)
    
    if expiry == "1H":
        return now + timedelta(hours=1)
    elif expiry == "1D":
        return now + timedelta(days=1)
    elif expiry == "1M":
        return now + timedelta(days=30)
    elif expiry == "1Y":
        return now + timedelta(days=365)
    else:
        raise ValueError(f"Invalid expiry format: {expiry}")


def generate_api_key() -> tuple[str, str]:
    """
    Generate a secure API key and its hash.
    Returns: (api_key, key_hash)
    """
    # Generate random API key with prefix
    random_part = secrets.token_urlsafe(32)
    api_key = f"sk_live_{random_part}"
    
    # Hash the key for storage
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    return api_key, key_hash


@router.post("/create", response_model=APIKeyCreateResponse)
async def create_api_key(
    request: APIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new API key for the authenticated user.
    
    Rules:
    - Maximum 5 active keys per user
    - Permissions must be explicitly assigned
    - Expiry is converted to datetime and stored
    """
    # Check active keys count
    active_keys_count = await db.execute(
        select(func.count(APIKey.id)).where(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True,
            APIKey.expires_at > datetime.now(timezone.utc)
        )
    )
    count = active_keys_count.scalar()
    
    if count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 5 active API keys allowed per user"
        )
    
    # Parse expiry
    try:
        expires_at = parse_expiry(request.expiry)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Generate API key
    api_key, key_hash = generate_api_key()
    
    # Create API key record
    new_key = APIKey(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=request.name,
        key_hash=key_hash,
        permissions=request.permissions,
        expires_at=expires_at,
        is_active=True
    )
    
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    return APIKeyCreateResponse(
        api_key=api_key,
        expires_at=expires_at
    )


@router.post("/rollover", response_model=APIKeyRolloverResponse)
async def rollover_api_key(
    request: APIKeyRolloverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Rollover an expired API key with the same permissions.
    
    Rules:
    - The expired key must truly be expired
    - The new key reuses the same permissions
    - New expiry is converted to datetime
    """
    # Fetch the expired key
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == request.expired_key_id,
            APIKey.user_id == current_user.id
        )
    )
    expired_key = result.scalar_one_or_none()
    
    if not expired_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or does not belong to you"
        )
    
    # Check if key is truly expired
    now = datetime.now(timezone.utc)
    if expired_key.expires_at > now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is not expired yet. Cannot rollover."
        )
    
    # Check active keys count (excluding the expired one)
    active_keys_count = await db.execute(
        select(func.count(APIKey.id)).where(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True,
            APIKey.expires_at > now
        )
    )
    count = active_keys_count.scalar()
    
    if count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 5 active API keys allowed per user"
        )
    
    # Parse new expiry
    try:
        expires_at = parse_expiry(request.expiry)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Generate new API key
    api_key, key_hash = generate_api_key()
    
    # Reuse permissions from expired key
    new_key = APIKey(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=expired_key.name,
        key_hash=key_hash,
        permissions=expired_key.permissions,
        expires_at=expires_at,
        is_active=True
    )
    
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    return APIKeyRolloverResponse(
        api_key=api_key,
        expires_at=expires_at
    )
