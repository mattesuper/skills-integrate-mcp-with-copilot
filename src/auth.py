"""Teacher credentials and short-lived, in-memory login sessions."""

import argparse
import getpass
import hashlib
import json
import secrets
from pathlib import Path
from threading import RLock
from time import monotonic

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field


TEACHERS_FILE = Path(__file__).with_name("teachers.json")
PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60
sessions: dict[str, tuple[str, float]] = {}
session_lock = RLock()
bearer = HTTPBearer(auto_error=False)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PASSWORD_ITERATIONS
    ).hex()


def login(credentials: LoginInput):
    teachers = json.loads(TEACHERS_FILE.read_text())
    record = teachers.get(credentials.username)
    # Unknown accounts take the same expensive verification path.
    salt = record["salt"] if record else "00" * 16
    expected = record["password_hash"] if record else "00" * 32
    valid = secrets.compare_digest(hash_password(credentials.password, salt), expected)
    if not valid or record is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    now = monotonic()
    token = secrets.token_urlsafe(32)
    with session_lock:
        for expired in [key for key, (_, expiry) in sessions.items() if expiry <= now]:
            del sessions[expired]
        sessions[token] = (credentials.username, now + SESSION_SECONDS)
    return {"access_token": token, "token_type": "bearer", "username": credentials.username}


def require_teacher(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    with session_lock:
        session = sessions.get(credentials.credentials) if credentials else None
        if session is not None and session[1] > monotonic():
            return session[0]
        if credentials:
            sessions.pop(credentials.credentials, None)
    raise HTTPException(
        status_code=401, detail="Teacher login required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    with session_lock:
        sessions.pop(credentials.credentials, None)
    return {"message": "Logged out"}


def main():
    parser = argparse.ArgumentParser(description="Assign or reset a teacher password")
    parser.add_argument("username")
    args = parser.parse_args()
    if not args.username.strip() or len(args.username) > 100:
        parser.error("Username must contain 1 to 100 characters")
    password = getpass.getpass("New password (at least 12 characters): ")
    if not 12 <= len(password) <= 1024:
        parser.error("Password must contain 12 to 1024 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    teachers = json.loads(TEACHERS_FILE.read_text())
    salt = secrets.token_hex(16)
    teachers[args.username] = {"salt": salt, "password_hash": hash_password(password, salt)}
    TEACHERS_FILE.write_text(json.dumps(teachers, indent=2) + "\n")
    print("Teacher saved. Restart the server to invalidate existing sessions.")


if __name__ == "__main__":
    main()
