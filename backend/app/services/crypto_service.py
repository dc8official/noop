from __future__ import annotations

import base64
import os
import re
from typing import Optional
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

_SALT = b"lnmp-alert-crypto-salt-v1"
_INFO = b"lnmp-aes-256-gcm-key-derivation"


def _get_aes_key() -> bytes:
    master_secret = settings.security.secret_key.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=_INFO,
    )
    return hkdf.derive(master_secret)


def encrypt_secret(plaintext: str) -> str:
    """
    Encrypts sensitive credentials (webhook secrets, SMTP passwords)
    using AES-256-GCM. Produces: ENC:v1:<nonce_b64>:<ciphertext_b64>
    """
    if not plaintext:
        return ""
    if plaintext.startswith("ENC:v1:"):
        return plaintext

    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    ct_b64 = base64.b64encode(ciphertext).decode("ascii")
    return f"ENC:v1:{nonce_b64}:{ct_b64}"


def decrypt_secret(ciphertext: str) -> str:
    """
    Decrypts an AES-256-GCM encrypted payload.
    Falls back to plaintext for unencrypted strings (backward compatibility).
    """
    if not ciphertext:
        return ""
    if not ciphertext.startswith("ENC:v1:"):
        return ciphertext

    parts = ciphertext.split(":")
    if len(parts) != 4:
        return ciphertext

    try:
        nonce = base64.b64decode(parts[2])
        raw_ct = base64.b64decode(parts[3])
        key = _get_aes_key()
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, raw_ct, None)
        return decrypted.decode("utf-8")
    except Exception:
        # Fall back gracefully if decryption fails
        return ciphertext


def mask_secret(secret: str) -> str:
    """
    Masks webhook URLs (e.g. https://.../invoke?sig=••••••••) and passwords (••••••••••••).
    """
    if not secret:
        return ""

    if secret.startswith("ENC:v1:"):
        secret = decrypt_secret(secret)

    if secret.startswith("http://") or secret.startswith("https://"):
        try:
            parsed = urlparse(secret)
            # Mask query parameters
            query_params = parse_qsl(parsed.query, keep_blank_values=True)
            sensitive_keys = {
                "sig", "token", "key", "secret", "webhook", "auth",
                "api_key", "password", "access_token", "apikey", "bearer", "code",
            }
            if query_params:
                masked_params = []
                for k, v in query_params:
                    if k.lower() in sensitive_keys:
                        masked_params.append((k, "••••••••"))
                    else:
                        masked_params.append((k, v))
                new_query = unquote(urlencode(masked_params))
            else:
                new_query = parsed.query

            path = parsed.path
            # Mask webhook path tokens (e.g. Discord: /api/webhooks/<id>/<token>)
            if "/api/webhooks/" in path:
                segments = path.strip("/").split("/")
                if len(segments) >= 3:
                    # segments[0] = api, segments[1] = webhooks, segments[2] = id, segments[3] = token
                    segments[-1] = "••••••••"
                    path = "/" + "/".join(segments)
            # Mask Slack webhook path (e.g. /services/T.../B.../token)
            elif "/services/T" in path:
                segments = path.strip("/").split("/")
                if len(segments) >= 3:
                    segments[-1] = "••••••••"
                    path = "/" + "/".join(segments)
            # Mask Microsoft Teams incoming webhook path (e.g. /IncomingWebhook/<token1>/<token2>)
            elif re.search(r"/IncomingWebhook/([^/]+)/([^/?]+)", path, flags=re.IGNORECASE):
                path = re.sub(
                    r"(/IncomingWebhook/)([^/]+)/([^/?]+)",
                    r"\1••••••••••••/••••••••••••",
                    path,
                    flags=re.IGNORECASE,
                )

            # Mask embedded basic auth credentials in netloc (e.g. https://user:pass@host/path)
            netloc = parsed.netloc
            if "@" in netloc:
                user_info, host = netloc.split("@", 1)
                if ":" in user_info:
                    user, _ = user_info.split(":", 1)
                    netloc = f"{user}:••••••••@{host}"
                else:
                    netloc = f"••••••••@{host}"

            masked_url = urlunparse((
                parsed.scheme,
                netloc,
                path,
                parsed.params,
                new_query,
                parsed.fragment,
            ))
            return masked_url
        except Exception:
            return "https://••••••••"

    return "••••••••••••"
