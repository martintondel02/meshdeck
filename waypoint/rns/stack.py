"""Owns the RNS.Reticulum instance lifecycle for the app."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import RNS
from RNS.vendor.configobj import ConfigObj

from waypoint.rns.config_gen import render_config

log = logging.getLogger(__name__)


class InvalidConfigError(ValueError):
    """Raised when a generated/edited Reticulum config is not bootable.

    Important: RNS os._exit(255)s on interface creation errors. We validate
    BEFORE constructing RNS.Reticulum so users get a readable error instead of
    a silently dead process.
    """


# Interface types where Waypoint checks for the keys they require to start.
_LISTENER_TYPES = {"TCPServerInterface", "BackboneInterface"}
_CLIENT_TYPES = {"TCPClientInterface", "BackboneClientInterface"}


def validate_interface_config(config_path: Path) -> None:
    """Validate a rendered Reticulum config; raises InvalidConfigError."""
    try:
        cfg = ConfigObj(str(config_path))
    except Exception as exc:  # noqa: BLE001
        raise InvalidConfigError(f"config file does not parse: {exc}") from None
    interfaces = cfg.get("interfaces", {})
    for name, body in interfaces.items():
        if not isinstance(body, dict):
            raise InvalidConfigError(f"interface [{name}] is malformed")
        itype = body.get("type")
        if not itype:
            raise InvalidConfigError(f'interface "{name}" is missing a "type" key')
        if itype in _LISTENER_TYPES:
            if not (body.get("port") or body.get("listen_port")):
                raise InvalidConfigError(
                    f'interface "{name}" ({itype}) needs "port" (or "listen_port")'
                )
            if not (body.get("listen_ip") or body.get("device")):
                raise InvalidConfigError(
                    f'interface "{name}" ({itype}) needs "listen_ip" (or "device");'
                    ' note: this Reticulum version does not accept "listen_on"'
                )
        elif itype in _CLIENT_TYPES:
            if not body.get("target_host") or not body.get("target_port"):
                raise InvalidConfigError(
                    f'interface "{name}" ({itype}) needs "target_host" and "target_port"'
                )


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
        config_path = self.write_config(log_file=log_file)
        validate_interface_config(config_path)
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
