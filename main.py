import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson.objectid import ObjectId
import secrets
import string

from database import db, create_document, get_documents

app = FastAPI(title="Rewards Token Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateTokensRequest(BaseModel):
    count: int = Field(1, ge=1, le=500, description="How many tokens to generate")
    value: float = Field(0, ge=0, description="Reward value per token")
    currency: str = Field("USD", min_length=1, max_length=6)
    purpose: Optional[str] = Field(None)
    expires_at: Optional[datetime] = Field(None, description="UTC timestamp when token expires")
    length: int = Field(10, ge=6, le=32, description="Token code length")
    prefix: Optional[str] = Field(None, description="Optional prefix for the token code, e.g., PROMO-")


class RedeemRequest(BaseModel):
    code: str = Field(..., description="Token code to redeem")
    client_id: str = Field(..., description="Identifier of the client redeeming the token")


class TokenPublic(BaseModel):
    code: str
    value: float
    currency: str
    purpose: Optional[str]
    expires_at: Optional[datetime]
    redeemed: bool
    redeemed_by: Optional[str]
    redeemed_at: Optional[datetime]
    created_at: Optional[datetime]


@app.get("/")
def read_root():
    return {"message": "Rewards Token API is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ------------------ Token Utilities ------------------

def _generate_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _ensure_unique_code(length: int, prefix: Optional[str]) -> str:
    attempts = 0
    while attempts < 10:
        code = _generate_code(length)
        if prefix:
            code = f"{prefix}{code}"
        existing = db["token"].find_one({"code": code})
        if not existing:
            return code
        attempts += 1
    raise HTTPException(status_code=500, detail="Could not generate a unique token code. Try again.")


# ------------------ Token Endpoints ------------------

@app.post("/api/tokens/generate", response_model=List[TokenPublic])
def generate_tokens(payload: GenerateTokensRequest):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    created: List[TokenPublic] = []
    for _ in range(payload.count):
        code = _ensure_unique_code(payload.length, payload.prefix)
        doc = {
            "code": code,
            "value": payload.value,
            "currency": payload.currency,
            "purpose": payload.purpose,
            "expires_at": payload.expires_at,
            "redeemed": False,
            "redeemed_by": None,
            "redeemed_at": None,
        }
        create_document("token", doc)
        created.append(TokenPublic(**doc))
    return created


@app.get("/api/tokens", response_model=List[TokenPublic])
def list_tokens(limit: int = 100, only_active: bool = False):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    now = datetime.now(timezone.utc)
    query = {}
    if only_active:
        query["redeemed"] = False
        # not expired or no expiry
        query["$or"] = [
            {"expires_at": {"$gt": now}},
            {"expires_at": {"$exists": False}},
            {"expires_at": None},
        ]

    docs = db["token"].find(query).sort("created_at", -1).limit(max(1, min(limit, 500)))
    out: List[TokenPublic] = []
    for d in docs:
        out.append(TokenPublic(
            code=d.get("code"),
            value=d.get("value", 0),
            currency=d.get("currency", "USD"),
            purpose=d.get("purpose"),
            expires_at=d.get("expires_at"),
            redeemed=d.get("redeemed", False),
            redeemed_by=d.get("redeemed_by"),
            redeemed_at=d.get("redeemed_at"),
            created_at=d.get("created_at"),
        ))
    return out


@app.get("/api/tokens/{code}", response_model=TokenPublic)
def get_token(code: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    doc = db["token"].find_one({"code": code})
    if not doc:
        raise HTTPException(status_code=404, detail="Token not found")
    return TokenPublic(
        code=doc.get("code"),
        value=doc.get("value", 0),
        currency=doc.get("currency", "USD"),
        purpose=doc.get("purpose"),
        expires_at=doc.get("expires_at"),
        redeemed=doc.get("redeemed", False),
        redeemed_by=doc.get("redeemed_by"),
        redeemed_at=doc.get("redeemed_at"),
        created_at=doc.get("created_at"),
    )


@app.post("/api/tokens/redeem", response_model=TokenPublic)
def redeem_token(payload: RedeemRequest):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    doc = db["token"].find_one({"code": payload.code})
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid token code")

    # Check if already redeemed
    if doc.get("redeemed"):
        raise HTTPException(status_code=400, detail="Token already redeemed")

    # Check expiry
    expires_at = doc.get("expires_at")
    if expires_at is not None:
        now = datetime.now(timezone.utc)
        if expires_at <= now:
            raise HTTPException(status_code=400, detail="Token has expired")

    # Mark as redeemed
    update = {
        "$set": {
            "redeemed": True,
            "redeemed_by": payload.client_id,
            "redeemed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    }
    db["token"].update_one({"_id": doc["_id"]}, update)
    updated = db["token"].find_one({"_id": doc["_id"]})

    return TokenPublic(
        code=updated.get("code"),
        value=updated.get("value", 0),
        currency=updated.get("currency", "USD"),
        purpose=updated.get("purpose"),
        expires_at=updated.get("expires_at"),
        redeemed=updated.get("redeemed", False),
        redeemed_by=updated.get("redeemed_by"),
        redeemed_at=updated.get("redeemed_at"),
        created_at=updated.get("created_at"),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
