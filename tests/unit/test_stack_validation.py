"""Pre-flight interface validation (protects against RNS os._exit on bad config)."""

import pytest

from meshdeck.config import DEFAULT_SETTINGS
from meshdeck.rns.config_gen import render_config
from meshdeck.rns.stack import InvalidConfigError, validate_interface_config


def _write(tmp_path, settings) -> object:
    path = tmp_path / "config"
    path.write_text(render_config(settings))
    return path


def test_valid_default_config(tmp_path):
    validate_interface_config(_write(tmp_path, dict(DEFAULT_SETTINGS)))


def test_valid_tcp_server_with_listen_ip(tmp_path):
    settings = dict(
        DEFAULT_SETTINGS,
        connect_autointerface=False,
        extra_config_text="  [[Srv]]\n    type = TCPServerInterface\n    enabled = yes\n"
        "    listen_ip = 127.0.0.1\n    port = 4242",
    )
    validate_interface_config(_write(tmp_path, settings))


def test_tcp_server_with_listen_on_is_rejected(tmp_path):
    settings = dict(
        DEFAULT_SETTINGS,
        connect_autointerface=False,
        extra_config_text="  [[Srv]]\n    type = TCPServerInterface\n    enabled = yes\n"
        "    listen_on = 127.0.0.1\n    port = 4242",
    )
    with pytest.raises(InvalidConfigError, match="listen_ip"):
        validate_interface_config(_write(tmp_path, settings))


def test_tcp_server_without_port_is_rejected(tmp_path):
    settings = dict(
        DEFAULT_SETTINGS,
        connect_autointerface=False,
        extra_config_text="  [[Srv]]\n    type = TCPServerInterface\n    enabled = yes\n"
        "    listen_ip = 127.0.0.1",
    )
    with pytest.raises(InvalidConfigError, match="port"):
        validate_interface_config(_write(tmp_path, settings))


def test_tcp_client_needs_host_and_port(tmp_path):
    settings = dict(
        DEFAULT_SETTINGS,
        public_entrypoints=[{"name": "Broken", "host": "", "port": 4242}],
        extra_config_text="  [[Cli]]\n    type = TCPClientInterface\n    enabled = yes\n"
        "    target_host = 127.0.0.1",
    )
    with pytest.raises(InvalidConfigError, match="target_port"):
        validate_interface_config(_write(tmp_path, settings))


def test_interface_without_type_is_rejected(tmp_path):
    settings = dict(
        DEFAULT_SETTINGS,
        connect_autointerface=False,
        extra_config_text="  [[Nope]]\n    enabled = yes",
    )
    with pytest.raises(InvalidConfigError, match="type"):
        validate_interface_config(_write(tmp_path, settings))
