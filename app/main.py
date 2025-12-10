from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import auth, api_keys, wallet


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    await init_db()
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="HNG Stage 9 - Wallet Service",
    description="Backend API for Wallet Management with Google Sign-In, API Keys, and Paystack Integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(wallet.router)


@app.get("/")
async def root():
    return {
        "message": "HNG Stage 9 - Wallet Service API",
        "endpoints": {
            "docs": "/docs",
            "google_auth": "/auth/google",
            "api_keys": "/keys/create",
            "wallet_deposit": "/wallet/deposit"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
