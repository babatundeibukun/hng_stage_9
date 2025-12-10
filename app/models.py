from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, Boolean, JSON
from sqlalchemy.sql import func
from datetime import datetime
import enum
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(String, nullable=True)  # Optional: link to user
    amount = Column(Integer, nullable=False)  # Amount in kobo
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    authorization_url = Column(String, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    key_hash = Column(String, unique=True, nullable=False)  # Hashed API key
    permissions = Column(JSON, nullable=False)  # Store as JSON array
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class Wallet(Base):
    __tablename__ = "wallets"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, unique=True, nullable=False, index=True)
    balance = Column(Integer, default=0, nullable=False)  # Balance in kobo
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Transfer(Base):
    __tablename__ = "transfers"
    
    id = Column(String, primary_key=True, index=True)
    sender_id = Column(String, nullable=False, index=True)
    recipient_id = Column(String, nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Amount in kobo
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.SUCCESS, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


