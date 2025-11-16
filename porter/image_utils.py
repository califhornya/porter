import base64
import io
from pathlib import Path

from PIL import Image


def image_to_data_url(image_path: Path) -> str:
    """Return a JPEG-compressed data URL for the provided image."""

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        max_dim = 1024
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        payload = buffer.getvalue()

    b64 = base64.b64encode(payload).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
