"""Fernet encryption for per-user provider keys."""

import base64
import binascii
import hashlib
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SECRETS_FILE = Path(os.environ.get("SECRETS_KEY_FILE") or _PROJECT_ROOT / ".secrets_key")


def _derive_fernet_key(material: str) -> bytes:
    """Accept a Fernet key or derive one deterministically from a passphrase."""
    material = material.strip()
    try:
        decoded = base64.urlsafe_b64decode(material)
        if len(decoded) == 32:
            return material.encode("ascii")
    except ValueError, binascii.Error:
        pass
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _load_or_create_master_key() -> bytes:
    """Read SECRETS_ENCRYPTION_KEY, or generate a new one and persist it."""
    env_key = os.environ.get("SECRETS_ENCRYPTION_KEY", "").strip()
    if env_key:
        return _derive_fernet_key(env_key)
    if _SECRETS_FILE.is_file():
        return _derive_fernet_key(_SECRETS_FILE.read_text().strip())
    key = Fernet.generate_key()
    _SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRETS_FILE.write_text(key.decode("ascii"))
    os.chmod(_SECRETS_FILE, 0o600)
    log.warning(
        "Generated a new SECRETS_ENCRYPTION_KEY at %s (chmod 600). "
        "Back this file up — provider keys at rest are unrecoverable without it. "
        "To rotate, see scripts/rotate-secrets.sh.",
        _SECRETS_FILE,
    )
    return key


# Rotations require a restart to replace this process-local value.
_fernet: Fernet = Fernet(_load_or_create_master_key())


def encrypt(plaintext: str) -> str:
    """Encrypt a provider key."""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a provider key, raising ValueError for invalid tokens."""
    try:
        return _fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt provider key (rotated master key?)") from e


def rotate_to(new_material: str) -> None:
    """Replace the active and persisted master after row re-encryption."""
    global _fernet
    _fernet = Fernet(_derive_fernet_key(new_material))
    _SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRETS_FILE.write_text(new_material.strip())
    os.chmod(_SECRETS_FILE, 0o600)


def key_file_path() -> Path:
    return _SECRETS_FILE
