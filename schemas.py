"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Example schemas (keep examples but add our Token schema)

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Reward Token schema
class Token(BaseModel):
    """
    Reward tokens to share with clients
    Collection name: "token"
    """
    code: str = Field(..., description="Unique token code to share")
    value: float = Field(0, ge=0, description="Reward value associated with the token")
    currency: str = Field("USD", description="Currency code for value")
    purpose: Optional[str] = Field(None, description="Reason or campaign for this token")
    expires_at: Optional[datetime] = Field(None, description="When the token expires (UTC)")
    redeemed: bool = Field(False, description="Whether the token has been redeemed")
    redeemed_by: Optional[str] = Field(None, description="Identifier of the client who redeemed it")
    redeemed_at: Optional[datetime] = Field(None, description="Timestamp when redeemed (UTC)")
    notes: Optional[str] = Field(None, description="Internal notes")
