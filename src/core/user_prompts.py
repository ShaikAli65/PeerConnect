from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class UserPrompts(Protocol):
    async def ask_discovery_peer_name(self, reason: str | None) -> str | None:
        """Ask the user for a peer host/name to help discovery."""

    async def ask_transfer_consent(self, peer_id: str) -> tuple[bool, bool | None]:
        """Ask whether an incoming transfer from peer_id should be accepted.

        Returns:
            tuple of (confirmed, remember_choice)
        """
