from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    """Schema for user creation."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str | None = None

class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str

class UserInfo(BaseModel):
    """Schema for returning user information."""
    uid: str
    email: EmailStr
    full_name: str | None = None
    # email_verified: bool

class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str 