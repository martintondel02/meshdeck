"""Owns the RNS.Reticulum instance lifecycle for the app."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import RNS

from waypoint.rns.config_gen import render_config

log = logging.getLogger(__name__)


class RnsStack:
    """Starts/stops the managed Reticulum instance using our generated config.

    NOTE: RNS does not expose a public clean-shutdown API for an in-process
    instance (rnsd handles signals externally). stop() is best-effort: within
    a normal app run the process exits and threads die with it.
    """

    def __init__(self, configdir: Path, settings_getter) -> None:
        self._configdir = configdir
        self._get_settings = settings_getter
        self._ret: RNS.Reticulum | None = None
        self.running = False

    def write_config(self, log_file: str | None = None) -> Path:
        config_text = render_config(self._get_settings(), log_file=log_file)
        config_path = self._configdir / "config"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(config_text, encoding="utf-8")
        return config_path

    def start(self, log_file: str | None = None) -> None:
        if self.running:
            return
        self.write_config(log_file=log_file)
        self._ret = RNS.Reticulum(configdir=str(self._configdir))
        self.running = True
        log.info("Reticulum started (configdir=%s)", self._configdir)

    def stop(self) -> None:
        self.running = False
        self._ret = None

    def interfaces(self) -> list[dict[str, Any]]:
        if not self.running:
            return []
        result = []
        for iface in RNS.Transport.interfaces:
            result.append(
                {
                    "name": str(iface),
                    "type": type(iface).__name__,
                    "online": bool(getattr(iface, "online", False)),
                    "bitrate": getattr(iface, "bitrate", None),
                }
            )
        return result

    def transport_enabled(self) -> bool:
        return bool(self._get_settings().get("transport_enabled", False))
