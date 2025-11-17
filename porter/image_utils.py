import base64
import colorsys
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image

# Rough hue centers (0-360) for Riftbound domains
DOMAIN_HUES: Dict[str, float] = {
    "FURY": 0.0,  # red
    "CALM": 125.0,  # green
    "MIND": 210.0,  # blue
    "BODY": 30.0,  # orange
    "CHAOS": 285.0,  # purple
    "ORDER": 55.0,  # yellow / gold
}


@dataclass
class DomainColorSample:
    """Summary of domain hues found in an image region."""

    domains: List[str]
    confidence: float
    weights: Dict[str, float]


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


def _power_icon_crop_box(size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Return a bounding box for the cost/power icon region.

    The power icons live near the upper-right corner of the card frame. We take a
    generous slice of that area to ensure the icons are inside the crop across
    different aspect ratios.
    """

    width, height = size
    left = int(width * 0.60)
    top = int(height * 0.02)
    right = int(width * 0.98)
    bottom = int(height * 0.20)
    return left, top, right, bottom


def _nearest_domain(hue: float) -> Tuple[str, float]:
    """Return the closest domain and similarity score for a hue (0-360)."""

    best_domain = ""
    best_distance = 999.0
    for domain, center in DOMAIN_HUES.items():
        distance = abs(hue - center)
        distance = min(distance, 360.0 - distance)
        if distance < best_distance:
            best_distance = distance
            best_domain = domain

    # Convert distance into a [0, 1] confidence-like score
    score = max(0.0, 1.0 - best_distance / 50.0)
    return best_domain, score


def infer_domains_from_image(image_path: Path) -> DomainColorSample:
    """Infer probable domain colors from the power icon region of the image."""

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        region = img.crop(_power_icon_crop_box(img.size))
        region = region.resize((64, 64), Image.LANCZOS)

    hues: List[float] = []
    for r, g, b in region.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        if s < 0.35 or v < 0.25:
            continue
        hues.append(h * 360.0)

    if not hues:
        return DomainColorSample(domains=[], confidence=0.0, weights={})

    weights: Dict[str, float] = {domain: 0.0 for domain in DOMAIN_HUES}
    for hue in hues:
        domain, score = _nearest_domain(hue)
        weights[domain] += score

    total_weight = sum(weights.values()) or 1.0
    ordered = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    primary_domain, primary_weight = ordered[0]
    confidence = min(1.0, primary_weight / total_weight)

    domains: List[str] = [primary_domain]
    if len(ordered) > 1:
        second_domain, second_weight = ordered[1]
        if second_weight / total_weight >= 0.25:
            domains.append(second_domain)

    return DomainColorSample(domains=domains, confidence=confidence, weights=weights)
