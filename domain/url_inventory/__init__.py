"""Domain types for the per-project URL inventory."""

from domain.url_inventory.entry import (
    UrlFinding,
    UrlSource,
    UrlTool,
)
from domain.url_inventory.vendor_filter import (
    VENDOR_INDICATORS,
    is_vendor_path,
)

__all__ = [
    "UrlFinding",
    "UrlSource",
    "UrlTool",
    "VENDOR_INDICATORS",
    "is_vendor_path",
]
