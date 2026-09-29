"""Domain port and value object for Burp Organizer item fetching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OrganizerItem:
    """Single item from Burp's Organizer.

    ``response`` is ``"<no response>"`` when the item
    was sent from a request-only context.
    """

    id: int
    status: str
    request: str
    response: str
    notes: str


class OrganizerFetcherPort(Protocol):
    """Driven port: fetch Organizer items from Burp."""

    def fetch_items(self) -> list[OrganizerItem]: ...
