from __future__ import annotations

import base64
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def decode_user_identity(raw_header: str) -> tuple[str, str]:
    """
    Decode the base64-encoded email from the request header.

    Returns
    -------
    user_id  : base64 string (stored in collection for isolation)
    email_id : plain email string (stored for human-readable reference)
    """
    token = raw_header.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    try:
        padded   = token + "=" * (-len(token) % 4)
        email_id = base64.b64decode(padded).decode("utf-8").strip()
    except Exception:
        email_id = token

    user_id = token
    return user_id, email_id
