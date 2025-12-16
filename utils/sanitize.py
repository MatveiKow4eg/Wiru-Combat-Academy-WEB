import re
from typing import Optional

import bleach

# Precompile dangerous patterns for quick detection
DANGEROUS_PATTERNS = [
    re.compile(r"<\s*(script|img|svg|iframe|object|embed)[^>]*", re.I),
    re.compile(r"on[a-zA-Z]+\s*=", re.I),
    re.compile(r"javascript\s*:\s*", re.I),
    re.compile(r"<\s*/\s*script\s*>", re.I),
    re.compile(r"<[a-z][^>]*>", re.I),  # any HTML tag
]


def contains_dangerous_input(value: Optional[str]) -> bool:
    if not value:
        return False
    for pat in DANGEROUS_PATTERNS:
        if pat.search(value):
            return True
    return False


def sanitize_plain_text(value: Optional[str]) -> str:
    """
    Convert any input into safe plain text suitable for storing and rendering.
    - remove all HTML tags and attributes (bleach with tags=[], attributes={}, strip=True)
    - neutralize common XSS vectors like javascript:, on*=, <script, <img, <svg, etc.
    - trim and normalize spaces
    """
    if value is None:
        return ""
    # First, bleach-clean to strip HTML
    cleaned = bleach.clean(value, tags=[], attributes={}, strip=True)

    # Remove/neutralize protocol and event-handler leftovers
    cleaned = re.sub(r"javascript\s*:\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"on([a-zA-Z]+)\s*=", r"on\1 =", cleaned, flags=re.I)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
