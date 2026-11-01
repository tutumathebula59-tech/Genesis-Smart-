# auth_backend.py
#
# Drop-in FastAPI router for sign-in. Primary flow is wallet-based
# (MetaMask / WalletConnect via a signed message, à la Sign-In-With-Ethereum);
# the original username+password + forgot-password flow is kept below as an
# optional legacy fallback — the frontend no longer calls it, but you can
# re-wire a password LoginScreen to it if you want a non-wallet option too.
#
# Setup:
#   pip install fastapi bcrypt pyjwt eth-account
#   export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
#
# Wire into your existing app:
#   from auth_backend import router as auth_router
#   app.include_router(auth_router)
#
# IMPORTANT: SEED_USERS/WALLET_ALLOWLIST are in-memory placeholders — swap
# for your real user store before exposing this hub outside your home network.

import os
import time
import secrets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import bcrypt
import jwt
from eth_account import Account
from eth_account.messages import encode_defunct

router = APIRouter()
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGO = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
RESET_CODE_TTL_SECONDS = 60 * 15      # 15 minutes
NONCE_TTL_SECONDS = 60 * 5            # 5 minutes to connect + sign

# ---------------------------------------------------------------------------
# Wallet login (SIWE-style: sign a message, no on-chain transaction)
# ---------------------------------------------------------------------------
NONCES = {}  # address (lowercase) -> { nonce, expires_at }

# Optional allowlist: if non-empty, only these addresses (lowercase) may log
# in. Leave empty during setup/testing to let any wallet that can sign in —
# tighten this before exposing the hub outside your home network.
WALLET_ALLOWLIST: set[str] = set()


class WalletVerifyRequest(BaseModel):
    address: str
    message: str
    signature: str


@router.get("/auth/wallet-nonce")
def wallet_nonce(address: str):
    addr = address.lower()
    nonce = secrets.token_hex(8)
    NONCES[addr] = {"nonce": nonce, "expires_at": time.time() + NONCE_TTL_SECONDS}
    return {"nonce": nonce}


@router.post("/auth/wallet-verify")
def wallet_verify(req: WalletVerifyRequest):
    addr = req.address.lower()
    entry = NONCES.get(addr)
    if not entry or time.time() > entry["expires_at"]:
        raise HTTPException(status_code=400, detail="Nonce expired — reconnect your wallet and try again.")
    if entry["nonce"] not in req.message:
        raise HTTPException(status_code=400, detail="Nonce mismatch.")

    try:
        signable = encode_defunct(text=req.message)
        recovered = Account.recover_message(signable, signature=req.signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Couldn't verify that signature.")

    if recovered.lower() != addr:
        raise HTTPException(status_code=401, detail="Signature does not match the wallet address.")

    if WALLET_ALLOWLIST and addr not in WALLET_ALLOWLIST:
        raise HTTPException(status_code=403, detail="This wallet isn't authorized for this hub.")

    del NONCES[addr]  # one-time use
    token = jwt.encode(
        {"sub": addr, "auth": "wallet", "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        JWT_SECRET, algorithm=JWT_ALGO,
    )
    short = f"{req.address[:6]}\u2026{req.address[-4:]}"
    return {"token": token, "username": short, "address": req.address}


# ---------------------------------------------------------------------------
# Legacy username/password + forgot-password flow (kept for optional use —
# not called by the current frontend, which is wallet-only)
# ---------------------------------------------------------------------------

def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def _check(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

SEED_USERS = {
    "admin": {"username": "admin", "email": "admin@example.com", "password_hash": _hash("genesis")},
}
RESET_CODES = {}  # identifier -> { code, expires_at }

def find_user(identifier: str):
    for u in SEED_USERS.values():
        if u["username"] == identifier or u["email"] == identifier:
            return u
    return None

class LoginRequest(BaseModel):
    username: str
    password: str

class ResetRequest(BaseModel):
    identifier: str

class ResetConfirm(BaseModel):
    identifier: str
    code: str
    password: str

@router.post("/auth/login")
def login(req: LoginRequest):
    user = find_user(req.username)
    if not user or not _check(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    token = jwt.encode(
        {"sub": user["username"], "auth": "password", "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        JWT_SECRET, algorithm=JWT_ALGO,
    )
    return {"token": token, "username": user["username"]}

@router.post("/auth/reset-request")
def reset_request(req: ResetRequest):
    # Always return ok, whether or not the account exists — don't leak that info.
    user = find_user(req.identifier)
    if user:
        code = f"{secrets.randbelow(1_000_000):06d}"
        RESET_CODES[req.identifier] = {"code": code, "expires_at": time.time() + RESET_CODE_TTL_SECONDS}
        # TODO: actually send this code via email/SMS. For now, log it locally:
        print(f"[auth] password reset code for {req.identifier}: {code}")
    return {"ok": True}

@router.post("/auth/reset-confirm")
def reset_confirm(req: ResetConfirm):
    entry = RESET_CODES.get(req.identifier)
    if not entry or entry["code"] != req.code or time.time() > entry["expires_at"]:
        raise HTTPException(status_code=400, detail="That code is invalid or expired.")
    user = find_user(req.identifier)
    if not user:
        raise HTTPException(status_code=400, detail="That code is invalid or expired.")
    user["password_hash"] = _hash(req.password)
    del RESET_CODES[req.identifier]
    return {"ok": True}

@router.get("/auth/me")
def me(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return {"username": payload["sub"]}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
