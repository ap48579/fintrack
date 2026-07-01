"""Generates a VAPID keypair for Web Push. Run once: `uv run python -m app.core.vapid`,
then copy the printed values into backend/.env. Both keys are base64url-encoded raw bytes —
the format pywebpush's `Vapid.from_string()` and the browser's `PushManager.subscribe()`
`applicationServerKey` both expect directly, no PEM conversion needed."""

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from py_vapid.utils import b64urlencode, num_to_bytes


def generate_vapid_keypair() -> tuple[str, str]:
    """Returns (public_key_b64url, private_key_b64url)."""
    vapid = Vapid()
    vapid.generate_keys()

    private_value = vapid.private_key.private_numbers().private_value
    private_b64url = b64urlencode(num_to_bytes(private_value, 32))

    public_bytes = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_b64url = b64urlencode(public_bytes)

    return public_b64url, private_b64url


if __name__ == "__main__":
    public_key, private_key = generate_vapid_keypair()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
