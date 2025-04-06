# api_security.py
"""
Security middleware and utilities for the MT5 API server
"""
import os
import time
import uuid
import hashlib
import hmac
import secrets
from typing import List, Dict, Optional, Callable
from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "60"))
API_KEY_HEADER = "X-API-Key"
DEFAULT_API_KEY = os.getenv("API_KEY", "")  # Set a default API key in .env file
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173").split(",")

# Initialize API key header authentication
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)

# In-memory request tracking for rate limiting
request_tracker: Dict[str, List[float]] = {}


class ClientInfo(BaseModel):
    """Client information model for API requests"""
    ip: str
    api_key: Optional[str] = None
    user_agent: Optional[str] = None


def get_client_info(request: Request) -> ClientInfo:
    """Extract client information from the request"""
    client_ip = request.client.host if request.client else "unknown"
    api_key = request.headers.get(API_KEY_HEADER)
    user_agent = request.headers.get("User-Agent", "")

    return ClientInfo(
        ip=client_ip,
        api_key=api_key,
        user_agent=user_agent
    )


def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify the API key"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key missing")

    # For production, you might use a database of valid API keys
    # or a more sophisticated validation method
    if api_key != DEFAULT_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return api_key


def generate_api_key() -> str:
    """Generate a new API key"""
    # Generate a random key
    raw_key = secrets.token_hex(16)
    return raw_key


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to implement rate limiting"""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for certain paths like health check
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        client_info = get_client_info(request)
        client_id = client_info.ip

        # Check rate limit
        current_time = time.time()

        # Initialize or clean up client's request history
        if client_id not in request_tracker:
            request_tracker[client_id] = []
        else:
            # Remove requests older than 1 minute
            request_tracker[client_id] = [t for t in request_tracker[client_id]
                                          if current_time - t < 60]

        # Check if rate limit is exceeded
        if len(request_tracker[client_id]) >= MAX_REQUESTS_PER_MINUTE:
            return HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS_PER_MINUTE} requests per minute allowed."
            )

        # Add current request timestamp
        request_tracker[client_id].append(current_time)

        # Process the request
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'"

        return response


class IPAllowListMiddleware(BaseHTTPMiddleware):
    """Middleware to restrict access by IP address"""

    def __init__(self, app, allowed_ips=None):
        super().__init__(app)
        # Load allowed IPs from environment variable or use default
        self.allowed_ips = os.getenv("ALLOWED_IPS", "").split(",") if allowed_ips is None else allowed_ips

        # If no IPs are specified, allow all
        self.restrict_by_ip = bool(self.allowed_ips and self.allowed_ips[0])

    async def dispatch(self, request: Request, call_next):
        if self.restrict_by_ip:
            client_ip = request.client.host if request.client else None

            if not client_ip or client_ip not in self.allowed_ips:
                return HTTPException(status_code=403, detail="Access denied from your IP address")

        return await call_next(request)


# Functions to add to api_server.py

def configure_security(app):
    """Configure security for the FastAPI application"""
    from fastapi.middleware.cors import CORSMiddleware

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,  # Restrict to specific origins in production
        allow_credentials=True,
        allow_methods=["*"],  # Could be restricted to specific methods
        allow_headers=["*"],  # Could be restricted to specific headers
    )

    # Add rate limiting
    app.add_middleware(RateLimitMiddleware)

    # Add IP restriction if enabled
    app.add_middleware(IPAllowListMiddleware)

    # Create API key if not exists
    if not DEFAULT_API_KEY:
        new_api_key = generate_api_key()
        print(f"WARNING: No API key found in environment. Generated temporary key: {new_api_key}")
        print("For security, set this in your .env file as API_KEY=your-key")

    return app


# Usage of API key in endpoints:
"""
To protect endpoints with API key authentication, add the Depends(verify_api_key) 
parameter to your FastAPI route functions.

Example:
@app.get("/protected-endpoint")
async def protected_endpoint(api_key: str = Depends(verify_api_key)):
    return {"message": "This endpoint is protected"}
"""