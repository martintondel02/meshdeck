"""Waypoint's Reticulum identity: load or create the private key."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import RNS

log = logging.getLogger(__name__)


class IdentityManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._identity: RNS.Identity | None = None

    def load_or_create(self) -> RNS.Identity:
        if self.path.exists():
            identity = RNS.Identity.from_file(str(self.path))
            if identity is None:
                raise RuntimeError(f"Could not load identity from {self.path}")
            log.info("Loaded existing identity")
        else:
            identity = RNS.Identity()
            if not identity.to_file(str(self.path)):
                raise RuntimeError(f"Could not write identity to {self.path}")
            os.chmod(self.path, 0o600)
            log.info("Created new identity")
        self._identity = identity
        return identity

    @property
    def identity(self) -> RNS.Identity:
        assert self._identity is not None, "load_or_create() has not run"
        return self._identity

    @property
    def hash_hex(self) -> str:
        return self.identity.hash.hex()
