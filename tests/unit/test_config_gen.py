"""Snapshot-style tests for the generated Reticulum config."""

from meshdeck.config import DEFAULT_SETTINGS
from meshdeck.rns.config_gen import render_config


def test_default_basic_mode_config():
    config = render_config(dict(DEFAULT_SETTINGS), log_file="/data/logs/reticulum.log")
    assert "enable_transport = No" in config
    assert "share_instance = No" in config
    assert "loglevel = 4" in config
    assert "logfile = /data/logs/reticulum.log" in config
    assert "type = AutoInterface" in config
    assert "TCPClientInterface" not in config


def test_no_autointerface_no_interfaces_rendered():
    settings = dict(DEFAULT_SETTINGS, connect_autointerface=False)
    config = render_config(settings)
    assert "[interfaces]" in config
    assert "AutoInterface" not in config


def test_public_entrypoints_and_transport():
    settings = dict(
        DEFAULT_SETTINGS,
        transport_enabled=True,
        public_entrypoints=[
            {"name": "Dublin 1", "host": "dublin.connect.reticulum.network", "port": 4965},
            {"name": "BetweenTheBorders", "host": "reticulum.betweentheborders.com", "port": 4242},
        ],
    )
    config = render_config(settings)
    assert "enable_transport = Yes" in config
    assert "[[Dublin 1]]" in config
    assert "target_host = dublin.connect.reticulum.network" in config
    assert "target_port = 4965" in config
    assert "[[BetweenTheBorders]]" in config


def test_extra_config_text_is_appended():
    settings = dict(
        DEFAULT_SETTINGS,
        extra_config_text="  [[Test Server]]\n    type = TCPServerInterface\n"
        "    enabled = yes\n    listen_on = 127.0.0.1\n    port = 4255",
    )
    config = render_config(settings)
    assert "type = TCPServerInterface" in config
    assert config.rstrip().endswith("port = 4255")


def test_values_cannot_inject_newlines():
    settings = dict(
        DEFAULT_SETTINGS,
        public_entrypoints=[{"name": "evil\n[injected]", "host": "x.example", "port": 1}],
    )
    config = render_config(settings)
    assert "[injected]" not in config.split("[reticulum]")[0]  # injected section impossible
    assert "evil [injected]" in config  # newline neutralized into a space
