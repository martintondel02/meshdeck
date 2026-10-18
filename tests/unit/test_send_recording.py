"""Outbound message recording must create the peer row (FK race regression)."""

from __future__ import annotations

import asyncio

from meshdeck.config import AppPaths
from meshdeck.core.service import CoreService
from meshdeck.storage import messages as msg_repo
from meshdeck.storage import peers as peer_repo
from meshdeck.storage.db import Database

PEER = "ab" * 16
MSG = "cd" * 16


class FakeChat:
    """Stands in for ChatRouter after LXMF has accepted the message."""

    def send(self, *_args, **_kwargs) -> str:
        return MSG

    def send_file(self, *_args, **_kwargs) -> str:
        return MSG


async def test_send_to_peer_without_row_creates_it(tmp_path):
    paths = AppPaths(data_dir=tmp_path)
    paths.ensure()
    svc = CoreService(paths)
    svc.db = Database(paths.db_path)
    svc.db.open()
    svc.chat = FakeChat()  # type: ignore[assignment]
    svc.bus.bind(asyncio.get_running_loop())
    try:
        assert peer_repo.get_peer(svc.db, PEER) is None
        result = svc.send_message(PEER, "hello before the announce")
        assert result["state"] == "sending"

        peer = peer_repo.get_peer(svc.db, PEER)
        assert peer is not None
        assert peer["hash"] == PEER
        msg = msg_repo.get_message(svc.db, MSG)
        assert msg is not None
        assert msg["peer_hash"] == PEER
        assert msg["content"] == "hello before the announce"
    finally:
        svc.db.close()
