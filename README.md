# HNG Stage 9 - Wallet Service with Paystack Integration

This FastAPI application implements a complete wallet service with Google Sign-In authentication, API key management, Paystack deposits, and wallet-to-wallet transfers.

## Features

- **Google OAuth 2.0 Authentication**: Server-side sign-in flow with JWT token generation
- **API Key Management**: Create, rollover, and manage API keys for service-to-service access
- **Wallet System**: User wallets with balance tracking
- **Paystack Deposits**: Initialize deposits and webhook handling
- **Wallet Transfers**: Transfer funds between user wallets
- **Transaction History**: Track all wallet operations
- **Dual Authentication**: JWT (for users) and API keys (for services)

## Project Structure

```
hng_stage_9/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration settings
│   ├── database.py          # Database connection and session
│   ├── models.py            # SQLAlchemy models (User, APIKey, Transaction, Wallet)
│   ├── schemas.py           # Pydantic schemas
│   ├── auth_utils.py        # JWT and authentication utilities
│   └── routers/
│       ├── __init__.py
│       ├── auth.py          # Google OAuth endpoints
│       ├── api_keys.py      # API key management endpoints
│       └── payments.py      # Paystack payment endpoints
├── .env                     # Environment variables (create from .env.example)
├── .env.example             # Example environment variables
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup Instructions

### 1. Prerequisites

- Python 3.9 or higher
- PostgreSQL database
- Google Cloud Console account (for OAuth credentials)
- Paystack account (for payment integration)

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Set Up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google+ API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
5. Choose "Web application"
6. Add authorized redirect URI: `http://localhost:8000/auth/google/callback`
7. Copy the Client ID and Client Secret

### 4. Set Up Paystack

1. Sign up at [Paystack](https://paystack.com/)
2. Go to Settings → API Keys & Webhooks
3. Copy your Secret Key (use test key for development)
4. Set up webhook URL: `http://your-domain.com/payments/paystack/webhook`
5. Copy the webhook secret

### 5. Configure Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your credentials
```

Update `.env` with your actual values:

```env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/hng_stage_9

GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

PAYSTACK_SECRET_KEY=sk_test_your_paystack_secret_key_here
PAYSTACK_WEBHOOK_SECRET=your_paystack_webhook_secret_here

APP_SECRET_KEY=generate_a_random_secret_key_here
```

### 6. Set Up Database

```bash
# Create PostgreSQL database
createdb hng_stage_9

# Or using psql:
psql -U postgres
CREATE DATABASE hng_stage_9;
\q
```

### 7. Run the Application

```bash
# Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

## API Endpoints

### Authentication

#### 1. Trigger Google Sign-In
```
GET /auth/google
```
Returns the Google OAuth consent page URL.

**Response:**
```json
{
  "google_auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
}
```

#### 2. Google OAuth Callback
```
GET /auth/google/callback?code=xxx
```
Handles the OAuth callback, creates/updates user, and returns JWT token.

**Response:**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### API Key Management

#### 3. Create API Key
```
POST /keys/create
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "name": "wallet-service",
  "permissions": ["deposit", "transfer", "read"],
  "expiry": "1D"
}
```
Creates a new API key with specified permissions. Maximum 5 active keys per user.

**Expiry Options**: `1H` (1 hour), `1D` (1 day), `1M` (1 month), `1Y` (1 year)

**Permissions**: `deposit`, `transfer`, `read`

**Response (200):**
```json
{
  "api_key": "sk_live_xxxxxxxxxxxxx",
  "expires_at": "2025-12-10T12:00:00Z"
}
```

#### 4. Rollover Expired API Key
```
POST /keys/rollover
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "expired_key_id": "FGH2485K6KK79GKG9GKGK",
  "expiry": "1M"
}
```
Creates a new API key using the same permissions as an expired key.

**Response (200):**
```json
{
  "api_key": "sk_live_xxxxxxxxxxxxx",
  "expires_at": "2026-01-09T12:00:00Z"
}
```

### Payments

#### 5. Initiate Payment
```
POST /payments/paystack/initiate
Content-Type: application/json

{
  "amount": 5000,
  "email": your email
}
```
Initializes a Paystack transaction. Amount is in kobo (smallest currency unit).

**Response (201):**
```json
{
  "reference": "txn_abc123",
  "authorization_url": "https://checkout.paystack.com/..."
}
```

#### 6. Webhook (Paystack → Your Server)
```
POST /payments/paystack/webhook
x-paystack-signature: signature_hash
```
Receives payment status updates from Paystack.

**Response:**
```json
{
  "status": true
}
```

#### 7. Check Transaction Status
```
GET /payments/{reference}/status?refresh=false
```
Returns the current status of a transaction.

**Response:**
```json
{
  "reference": "txn_abc123",
  "status": "success",
  "amount": 5000,
  "paid_at": "2025-12-06T10:30:00Z"
}
```

## Testing the Flow

### Google Sign-In Flow (JWT Authentication)

1. **Get Auth URL**:
   ```bash
   curl http://localhost:8000/auth/google
   ```

2. **Visit the URL** in browser and sign in with Google

3. **Get JWT token** from callback response

4. **Use JWT** in subsequent requests:
   ```bash
   curl -H "Authorization: Bearer <your_jwt_token>" \
     http://localhost:8000/keys/create
   ```

### API Key Management Flow

1. **Create API Key** (requires JWT):
   ```bash
   curl -X POST http://localhost:8000/keys/create \
     -H "Authorization: Bearer <jwt_token>" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "my-service",
       "permissions": ["deposit", "read"],
       "expiry": "1D"
     }'
   ```

2. **Use API Key** for wallet operations:
   ```bash
   curl -H "X-API-Key: sk_live_xxxxx" \
     http://localhost:8000/wallet/balance
   ```

3. **Rollover Expired Key**:
   ```bash
   curl -X POST http://localhost:8000/keys/rollover \
     -H "Authorization: Bearer <jwt_token>" \
     -H "Content-Type: application/json" \
     -d '{
       "expired_key_id": "key_id_here",
       "expiry": "1M"
     }'
   ```

### Payment Flow

1. **Initiate Payment**:
   ```bash
   curl -X POST http://localhost:8000/payments/paystack/initiate \
     -H "Content-Type: application/json" \
     -d '{"amount": 5000}'
   ```

2. **Visit authorization_url** to complete payment

3. **Check Status**:
   ```bash
   curl http://localhost:8000/payments/{reference}/status
   ```

4. **Refresh from Paystack**:
   ```bash
   curl http://localhost:8000/payments/{reference}/status?refresh=true
   ```

## Database Schema

### Users Table
- `id`: UUID primary key
- `email`: Unique user email
- `name`: User's full name
- `picture`: Profile picture URL
- `google_id`: Google user ID (unique)
- `created_at`, `updated_at`: Timestamps

### API Keys Table
- `id`: UUID primary key
- `user_id`: Foreign key to users
- `name`: Key name/description
- `key_hash`: SHA-256 hashed API key
- `permissions`: JSON array of permissions
- `expires_at`: Expiration datetime
- `is_active`: Boolean flag
- `created_at`: Creation timestamp
- `revoked_at`: Revocation timestamp (nullable)

### Transactions Table
- `id`: Auto-increment primary key
- `reference`: Unique transaction reference
- `user_id`: Optional link to user
- `amount`: Amount in kobo
- `status`: pending | success | failed
- `authorization_url`: Paystack checkout URL
- `paid_at`: Payment completion timestamp
- `created_at`, `updated_at`: Timestamps

## Security Features

✅ JWT authentication with HS256 algorithm  
✅ API key hashing (SHA-256)  
✅ Maximum 5 active API keys per user  
✅ API key expiration enforcement  
✅ Permission-based access control  
✅ Environment variables for sensitive data  
✅ Webhook signature verification  
✅ HTTPS required for production  
✅ Input validation with Pydantic  

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Success
- `201`: Created (payment initiated)
- `400`: Bad Request (invalid input)
- `401`: Unauthorized (invalid OAuth code)
- `402`: Payment Required (Paystack failure)
- `404`: Not Found (transaction not found)
- `500`: Internal Server Error

## Production Deployment

Before deploying to production:

1. ✅ Use production credentials (not test keys)
2. ✅ Set up proper CORS origins
3. ✅ Enable HTTPS/SSL
4. ✅ Configure webhook URL with public domain
5. ✅ Use environment-specific database
6. ✅ Set up proper logging
7. ✅ Add rate limiting
8. ✅ Implement authentication/authorization
9. ✅ Add monitoring and alerts

## Troubleshooting

### Database Connection Issues
- Check PostgreSQL is running
- Verify DATABASE_URL is correct
- Ensure database exists

### Google OAuth Issues
- Verify redirect URI matches exactly
- Check client ID and secret
- Enable Google+ API in console

### Paystack Issues
- Use test secret key for development
- Verify webhook signature
- Check amount is in kobo (multiply by 100)

## Step-by-Step Explanation

### How Google OAuth with JWT Works

1. **User Request**: User hits `/auth/google` endpoint
2. **Redirect to Google**: Server generates OAuth URL with your client ID and redirect URI
3. **User Signs In**: User authenticates with Google
4. **Code Exchange**: Google redirects back to `/auth/google/callback` with authorization code
5. **Token Request**: Server exchanges code for access token (server-to-server)
6. **Fetch User Info**: Server uses access token to get user's email, name, picture from Google
7. **Save to Database**: Create or update user record in PostgreSQL
8. **Generate JWT**: Server creates JWT token with user ID and email
9. **Return JWT**: Send JWT token to client for subsequent requests

### How API Key System Works

1. **Create Key**: User (with JWT) hits `/keys/create` with name, permissions, and expiry
2. **Validate Limit**: Server checks user has < 5 active keys
3. **Parse Expiry**: Convert `1H/1D/1M/1Y` to actual datetime
4. **Generate Key**: Create secure random key with `sk_live_` prefix
5. **Hash Key**: Hash the key with SHA-256 before storing
6. **Store in DB**: Save key_hash, permissions, expiry, user_id
7. **Return Plain Key**: Send plain API key to user (only time they see it)
8. **Future Requests**: User sends API key, server hashes and compares with stored hash
9. **Rollover**: When expired, user can create new key with same permissions

### How API Key Rollover Works

1. **Request Rollover**: User provides expired key ID and new expiry
2. **Verify Ownership**: Check key belongs to requesting user
3. **Check Expiration**: Verify key is truly expired
4. **Reuse Permissions**: Copy permissions from old key
5. **Generate New Key**: Create new secure key with same permissions
6. **Store New Key**: Save with new expiry datetime
7. **Return New Key**: Send new API key to user

### How Paystack Payment Works

1. **Initialize Payment**: Client hits `/payments/paystack/initiate` with amount in kobo
2. **Generate Reference**: Server creates unique transaction reference
3. **Call Paystack**: Server calls Paystack Initialize API with reference and amount
4. **Get Authorization URL**: Paystack returns checkout page URL
5. **Save Transaction**: Store transaction with "pending" status in database
6. **Return to Client**: Send authorization URL to client
7. **User Pays**: User visits URL and completes payment on Paystack
8. **Webhook Notification**: Paystack sends webhook to your server with payment status
9. **Verify Signature**: Server validates webhook is from Paystack
10. **Update Database**: Change transaction status to "success" or "failed"
11. **Check Status**: Client can query `/payments/{reference}/status` anytime

### Security Measures

- **JWT Tokens**: Signed with HS256, contain user ID and email, expire after 30 minutes
- **API Key Storage**: Keys are hashed with SHA-256, never stored in plain text
- **API Key Format**: `sk_live_` prefix with 32-byte random string
- **Expiry Enforcement**: Keys checked on every request, rejected if expired
- **Permission Control**: Each key has specific permissions (deposit, transfer, read)
- **Rate Limiting**: Maximum 5 active keys per user
- **Environment Variables**: All secrets stored in `.env` file, never in code
- **Webhook Signature**: Validates incoming webhooks using HMAC-SHA512
- **OAuth Flow**: Uses authorization code flow (not implicit)
- **Input Validation**: Pydantic models validate all inputs

## License

This project is for HNG Stage 9 task submission.
