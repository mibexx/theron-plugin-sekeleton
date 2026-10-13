"""The interface between the generic sync and one service."""

from __future__ import annotations

from dataclasses import dataclass, field

# Theron's requirement statuses: open | in_progress | hitl | done | failed | skipped | closed
STATUSES = ("open", "in_progress", "hitl", "done", "failed", "skipped", "closed")


@dataclass
class RemoteItem:
    """One item of the service – a Trello card, a Jira ticket, a GitHub issue …"""
    id: str
    title: str
    description: str = ""
    status: str = "open"          # already mapped to one of STATUSES
    group: str = ""               # becomes the epic in Theron (Trello: the list, Jira: the epic …)
    url: str = ""
    extra: dict = field(default_factory=dict)


class Adapter:
    """Implement these for your service. All methods are async; use ``self.ctx.http`` for requests."""

    name = "service"              # short, unique – part of the keys in ctx.storage

    def __init__(self, ctx):
        self.ctx = ctx

    def configured(self) -> bool:
        """True when all settings it needs are there (the sync stays off otherwise)."""
        raise NotImplementedError

    async def test(self) -> str:
        """Check the connection – return a short text (e.g. the account name) or raise."""
        raise NotImplementedError

    async def fetch(self) -> list[RemoteItem]:
        """Every item of the board / project / filter that is synced."""
        raise NotImplementedError

    async def create(self, title: str, description: str, status: str, group: str) -> RemoteItem:
        """Create an item for a Theron requirement and return it (with its id)."""
        raise NotImplementedError

    async def update(self, item_id: str, title: str, description: str, status: str) -> None:
        """Bring an existing item up to date with a Theron requirement."""
        raise NotImplementedError
