"""Security primitives.

This project originally used passlib.hash.bcrypt directly.

Notes:
  * bcrypt has a hard 72-byte password limit.
  * passlib 1.7.4 + newer bcrypt (4.x/5.x) can error at runtime.

To support long passphrases safely, we use passlib's bcrypt_sha256 scheme:
  - passwords are pre-hashed with SHA-256 then processed by bcrypt
  - avoids the 72-byte limit while retaining bcrypt's properties

Compatibility:
  - legacy bcrypt hashes can still be verified
  - on successful verification, hashes can be upgraded automatically
"""

from __future__ import annotations

from passlib.context import CryptContext


pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    ok, new_hash = pwd_context.verify_and_update(password, password_hash)
    return bool(ok), new_hash
