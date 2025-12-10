from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str
    
    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    
    # Paystack
    paystack_secret_key: str
    paystack_webhook_secret: str
    
    # Application
    app_secret_key: str
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def get_async_database_url(self) -> str:
        """Convert DATABASE_URL to async driver if needed"""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()
