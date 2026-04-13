from pydantic import BaseModel, EmailStr
from typing import Optional, List


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UpdateRoleRequest(BaseModel):
    role: str


class ConnectorAccessRequest(BaseModel):
    connectors: List[str]


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    connectors: Optional[List[str]] = []


class TokenResponse(BaseModel):
    token: str
    user: UserResponse
