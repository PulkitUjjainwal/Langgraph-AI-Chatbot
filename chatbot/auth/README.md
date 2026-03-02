# Authentication Module

JWT-based authentication system for the MI Chat Bot Feedback Dashboard.

## Overview

This module provides secure, role-based authentication for the feedback dashboard while keeping the main chatbot APIs public. It uses JWT (JSON Web Tokens) for stateless authentication with refresh token support.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Client                               │
│  (Next.js Frontend - feedback_system/)                      │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTP + JWT
                   │
┌──────────────────▼──────────────────────────────────────────┐
│               FastAPI Backend                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Dependencies (dependencies.py)                        │ │
│  │  - get_current_user()                                  │ │
│  │  - require_auth()                                      │ │
│  │  - require_super_admin()                               │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               │                                              │
│  ┌────────────▼───────────────────────────────────────────┐ │
│  │  JWT Handler (jwt_handler.py)                          │ │
│  │  - create_access_token()                               │ │
│  │  - create_refresh_token()                              │ │
│  │  - verify_token()                                      │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               │                                              │
│  ┌────────────▼───────────────────────────────────────────┐ │
│  │  Auth Service (service.py)                             │ │
│  │  - authenticate_user()                                 │ │
│  │  - create_user()                                       │ │
│  │  - generate_tokens()                                   │ │
│  └────────────┬───────────────────────────────────────────┘ │
│               │                                              │
│  ┌────────────▼───────────────────────────────────────────┐ │
│  │  Password Handler (password.py)                        │ │
│  │  - hash_password()                                     │ │
│  │  - verify_password()                                   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│           Database (auth_service.py)                         │
│  ┌──────────────────┐  ┌──────────────────────────────────┐ │
│  │  users table     │  │  refresh_tokens table            │ │
│  │  - id            │  │  - id                            │ │
│  │  - email         │  │  - user_id                       │ │
│  │  - password_hash │  │  - token_hash                    │ │
│  │  - role          │  │  - expires_at                    │ │
│  └──────────────────┘  └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Module Structure

```
chatbot/auth/
├── __init__.py           # Module exports
├── password.py           # Password hashing (bcrypt)
├── jwt_handler.py        # JWT token operations
├── models.py             # Pydantic request/response models
├── dependencies.py       # FastAPI dependency injection
├── service.py            # Business logic
└── README.md            # This file

chatbot/database/
├── auth_service.py       # Database operations
└── auth_schema.sql       # Database schema
```

## Components

### 1. Password Handler (`password.py`)

Handles secure password hashing and verification using bcrypt.

```python
from chatbot.auth.password import hash_password, verify_password

# Hash a password
hashed = hash_password("MySecurePass123!")
# Returns: $2b$12$...

# Verify password
is_valid = verify_password("MySecurePass123!", hashed)
# Returns: True
```

**Features:**
- bcrypt with 12 rounds (secure and performant)
- Automatic salt generation
- Timing-safe comparison

### 2. JWT Handler (`jwt_handler.py`)

Creates and verifies JWT tokens.

```python
from chatbot.auth.jwt_handler import create_access_token, verify_token

# Create access token (60 min expiry)
token = create_access_token({
    "user_id": 1,
    "email": "user@example.com",
    "role": "admin"
})

# Verify token
payload = verify_token(token, expected_type="access")
if payload:
    user_id = payload["user_id"]
    role = payload["role"]
```

**Token Types:**
- **Access Token**: Short-lived (60 minutes), used for API authentication
- **Refresh Token**: Long-lived (30 days), used to get new access tokens

**Payload Structure:**
```json
{
  "user_id": 1,
  "email": "user@example.com",
  "role": "admin",
  "exp": 1234567890,
  "iat": 1234567890,
  "type": "access"
}
```

### 3. Pydantic Models (`models.py`)

Request and response models for type safety and validation.

**Request Models:**
- `LoginRequest` - Email + password
- `RefreshTokenRequest` - Refresh token
- `LogoutRequest` - Refresh token to revoke
- `CreateUserRequest` - User creation with password validation
- `UpdateUserRequest` - User updates

**Response Models:**
- `TokenResponse` - Access + refresh tokens
- `UserResponse` - User info (no password)
- `UserListResponse` - Paginated user list

**Password Validation:**
```python
# Automatic validation on CreateUserRequest
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character
```

### 4. FastAPI Dependencies (`dependencies.py`)

Dependency injection for route protection.

**Usage:**

```python
from chatbot.auth.dependencies import require_auth, require_super_admin

# Require any authenticated user
@app.get("/protected")
async def protected_route(current_user = Depends(require_auth)):
    return {"user": current_user}

# Require super_admin role
@app.post("/admin/create-user")
async def create_user(
    data: CreateUserRequest,
    current_user = Depends(require_super_admin)
):
    # Only super_admin can access
    return {"message": "User created"}
```

**Dependencies:**
- `get_current_user()` - Verify JWT and return user
- `require_auth()` - Require any authenticated user
- `require_super_admin()` - Require super_admin role
- `require_admin()` - Require admin or super_admin role
- `get_optional_user()` - Optional authentication

### 5. Auth Service (`service.py`)

Business logic for authentication and user management.

**Key Methods:**

```python
from chatbot.auth.service import AuthService

auth_service = AuthService(db_service)

# Authenticate user
user = await auth_service.authenticate_user(
    email="user@example.com",
    password="SecurePass123!"
)

# Create user
new_user = await auth_service.create_user(
    username="john_doe",
    email="john@example.com",
    password="SecurePass123!",
    full_name="John Doe",
    role="user",
    creator_role="super_admin"
)

# Generate tokens
tokens = await auth_service.generate_tokens(user)
# Returns: {"access_token": "...", "refresh_token": "..."}

# Refresh access token
new_access_token = await auth_service.refresh_access_token(refresh_token)

# Logout (revoke refresh token)
await auth_service.logout(refresh_token)
```

### 6. Database Service (`../database/auth_service.py`)

Async MySQL operations for users and tokens.

**Key Methods:**

```python
from chatbot.database.auth_service import AuthDatabaseService

db = AuthDatabaseService(
    host="localhost",
    user="root",
    password="password",
    database="chatbot"
)

await db.initialize()

# User operations
user = await db.get_user_by_email("user@example.com")
user = await db.get_user_by_id(1)
user_id = await db.create_user(username, email, password_hash, full_name, role)
await db.update_user(user_id, full_name="New Name", role="admin")
await db.delete_user(user_id)  # Soft delete
await db.update_last_login(user_id)

# Token operations
await db.store_refresh_token(user_id, token, expires_days=30)
user_id = await db.verify_refresh_token(token)
await db.revoke_refresh_token(token)
await db.cleanup_expired_tokens()

# List users
result = await db.list_users(page=1, page_size=20, role="admin")
```

## Role-Based Access Control (RBAC)

### Roles

| Role | Numeric Level | Permissions |
|------|---------------|-------------|
| user | 1 | View feedback (read-only) |
| admin | 2 | View feedback, export data |
| super_admin | 3 | Full access, user management |

### Role Hierarchy

```python
roleHierarchy = {
    "super_admin": 3,
    "admin": 2,
    "user": 1
}
```

### Super Admin Protection

- Email whitelist in `settings.py`: `SUPER_ADMIN_EMAILS`
- Cannot create super_admin via API
- Cannot modify super_admin role
- Cannot delete super_admin users

### Endpoint Protection

```python
# Any authenticated user
@router.get("/feedback")
async def get_feedback(current_user = Depends(require_auth)):
    pass

# Super admin only
@router.post("/users/create")
async def create_user(current_user = Depends(require_super_admin)):
    pass
```

## Authentication Flow

### 1. Login Flow

```
1. User submits email + password
2. Backend verifies credentials (password.verify_password)
3. Backend creates access + refresh tokens (jwt_handler)
4. Backend stores refresh token in database (hashed)
5. Backend returns tokens to client
6. Client stores tokens in localStorage
7. Client includes access_token in Authorization header
```

### 2. API Request Flow

```
1. Client sends request with Authorization: Bearer <access_token>
2. Backend extracts token from header
3. Backend verifies token (jwt_handler.verify_token)
4. Backend fetches user from database
5. Backend checks user is active
6. Backend executes endpoint logic
7. Backend returns response
```

### 3. Token Refresh Flow

```
1. Access token expires (401 Unauthorized)
2. Client sends refresh token to /api/auth/refresh
3. Backend verifies refresh token in database
4. Backend checks token not revoked and not expired
5. Backend creates new access token
6. Backend returns new access token
7. Client retries original request with new token
```

### 4. Logout Flow

```
1. Client sends refresh token to /api/auth/logout
2. Backend marks refresh token as revoked in database
3. Backend returns success
4. Client clears localStorage
5. Client redirects to login page
```

## Security Features

### Password Security
- ✅ bcrypt hashing with 12 rounds
- ✅ Password strength validation
- ✅ Passwords never returned in responses
- ✅ Timing-safe comparison

### Token Security
- ✅ Short-lived access tokens (60 minutes)
- ✅ Long-lived refresh tokens (30 days)
- ✅ Refresh tokens stored hashed (SHA-256)
- ✅ Token revocation support
- ✅ JWT signature verification
- ✅ Token type verification (access vs refresh)

### Database Security
- ✅ Parameterized SQL queries (SQL injection prevention)
- ✅ Connection pooling
- ✅ Async operations (non-blocking)
- ✅ Indexes for performance

### Application Security
- ✅ Role-based access control
- ✅ Super admin protection
- ✅ Email whitelist for super admins
- ✅ User activation/deactivation
- ✅ Last login tracking

## Configuration

### Environment Variables

```env
# JWT Configuration
JWT_SECRET_KEY=your-secret-key-min-32-chars  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Super Admin Whitelist
SUPER_ADMIN_EMAILS=admin@marketinside.com,superadmin@marketinside.com

# MySQL Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DATABASE=chatbot
MYSQL_POOL_SIZE=5
```

### Settings Class

```python
from chatbot.config.settings import get_settings

settings = get_settings()

# JWT settings
settings.jwt_secret_key
settings.jwt_algorithm
settings.jwt_access_token_expire_minutes
settings.jwt_refresh_token_expire_days

# Super admin whitelist
settings.super_admin_emails
```

## API Endpoints

### Authentication Endpoints

- `POST /api/auth/login` - User login
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout (revoke refresh token)
- `GET /api/auth/me` - Get current user info

### User Management Endpoints (Super Admin Only)

- `POST /api/admin/users/create` - Create new user
- `GET /api/admin/users/list` - List users (paginated)
- `PATCH /api/admin/users/{id}` - Update user
- `DELETE /api/admin/users/{id}` - Soft delete user

### Protected Endpoints

All `/api/admin/feedback/*` endpoints require authentication.

## Usage Examples

### Backend Example

```python
from fastapi import FastAPI, Depends
from chatbot.auth.dependencies import require_auth, require_super_admin
from chatbot.auth.models import CreateUserRequest

app = FastAPI()

# Protected endpoint - any authenticated user
@app.get("/api/feedback")
async def get_feedback(current_user = Depends(require_auth)):
    user_role = current_user["role"]
    return {"message": f"Hello {user_role}"}

# Protected endpoint - super admin only
@app.post("/api/admin/users")
async def create_user(
    request: CreateUserRequest,
    current_user = Depends(require_super_admin)
):
    # Create user logic
    return {"message": "User created"}
```

### Frontend Example

```typescript
import { login, fetchWithAuth, logout } from '@/lib/api';

// Login
const loginData = await login('user@example.com', 'password');
// Tokens stored automatically in localStorage

// Make authenticated request
const response = await fetchWithAuth('/admin/feedback/list');
const data = await response.json();
// Token refresh handled automatically on 401

// Logout
await logout();
// Tokens cleared, redirects to login
```

## Error Handling

### Common Errors

| Status | Error | Cause | Solution |
|--------|-------|-------|----------|
| 401 | Invalid or expired token | Token expired or invalid | Refresh token or re-login |
| 401 | Invalid email or password | Wrong credentials | Check credentials |
| 403 | Super admin access required | Insufficient permissions | Login as super_admin |
| 403 | User account is inactive | Account deactivated | Contact admin |
| 400 | Email already exists | Duplicate email | Use different email |
| 400 | Password validation failed | Weak password | Meet password requirements |

### Error Response Format

```json
{
  "detail": "Invalid or expired token"
}
```

## Testing

### Unit Tests (Example)

```python
# Test password hashing
def test_password_hashing():
    password = "SecurePass123!"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

# Test JWT token
def test_jwt_token():
    data = {"user_id": 1, "role": "admin"}
    token = create_access_token(data)
    payload = verify_token(token, "access")
    assert payload["user_id"] == 1
    assert payload["role"] == "admin"
```

### Integration Tests (Example)

```python
from fastapi.testclient import TestClient

client = TestClient(app)

# Test login
response = client.post("/api/auth/login", json={
    "email": "admin@marketinside.com",
    "password": "Admin@123"
})
assert response.status_code == 200
data = response.json()
access_token = data["access_token"]

# Test protected route
response = client.get(
    "/api/admin/feedback/list",
    headers={"Authorization": f"Bearer {access_token}"}
)
assert response.status_code == 200
```

## Performance

### Benchmarks

- **Password hashing**: ~100-150ms (bcrypt with 12 rounds)
- **JWT creation**: <1ms
- **JWT verification**: <1ms
- **Database user lookup**: 2-5ms (with indexes)
- **Total auth overhead**: ~3-10ms per protected request

### Optimization Tips

1. **Database**: Use connection pooling (already implemented)
2. **Caching**: Cache user lookups (optional, not implemented)
3. **Indexes**: Ensure email and token_hash are indexed (already implemented)
4. **Token expiry**: Balance security vs UX (current: 60min access, 30d refresh)

## Troubleshooting

### Issue: "Database not available"

**Cause**: MySQL connection failed

**Solution**:
```bash
# Check MySQL is running
mysql -u root -p

# Verify credentials in .env
cat .env | grep MYSQL
```

### Issue: "Invalid or expired token"

**Cause**: Token expired or invalid

**Solution**:
- Check JWT_SECRET_KEY matches between token creation and verification
- Verify token not expired
- Try refreshing token or re-login

### Issue: "Super admin access required"

**Cause**: User is not super_admin

**Solution**:
- Check user role in database: `SELECT role FROM users WHERE email = '<email>';`
- Verify email in SUPER_ADMIN_EMAILS list
- Super admin role can only be set via database, not API

## Best Practices

### Security
1. ✅ Always use HTTPS in production
2. ✅ Generate strong JWT secret (min 32 chars)
3. ✅ Never commit JWT_SECRET_KEY to git
4. ✅ Use environment variables for secrets
5. ✅ Implement rate limiting on login endpoint
6. ✅ Log authentication failures
7. ✅ Regular security audits

### Development
1. ✅ Use type hints (Python) and TypeScript (frontend)
2. ✅ Validate all input with Pydantic models
3. ✅ Use async/await for database operations
4. ✅ Follow DRY principle
5. ✅ Write comprehensive tests
6. ✅ Document all public functions

### Database
1. ✅ Use connection pooling
2. ✅ Create indexes on frequently queried columns
3. ✅ Use parameterized queries (SQL injection prevention)
4. ✅ Regular backups
5. ✅ Monitor query performance

## License

Part of MI Chat Bot project. All rights reserved.

## Support

For issues or questions, refer to:
- `JWT_AUTH_SETUP_GUIDE.md` - Setup and testing guide
- `QUICK_START.md` - Quick setup guide
- `AUTH_IMPLEMENTATION_CHANGELOG.md` - Implementation details
