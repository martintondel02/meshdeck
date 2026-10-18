"""Unit tests for the structured interface list rendering (Phase 3)."""

from meshdeck.rns.config_gen import render_config, validate_interfaces


def _settings(**over):
    base = {
        "transport_enabled": False,
        "log_level": 4,
        "connect_autointerface": False,
        "public_entrypoints": [],
        "extra_config_text": "",
        "interfaces": [],
    }
    base.update(over)
    return base


def test_structured_interfaces_take_over_legacy_defaults():
    text = render_config(
        _settings(
            connect_autointerface=True,  # legacy default: would add AutoInterface
            interfaces=[
                {
                    "kind": "tcp_server",
                    "name": "My Server",
                    "enabled": True,
                    "listen_ip": "127.0.0.1",
                    "port": 4243,
                }
            ],
        )
    )
    assert "TCPServerInterface" in text
    assert "listen_ip = 127.0.0.1" in text
    assert "port = 4243" in text
    assert "AutoInterface" not in text  # structured list fully replaces legacy


def test_disabled_and_incomplete_entries_are_skipped():
    text = render_config(
        _settings(
            interfaces=[
                {"kind": "tcp_client", "name": "Off", "enabled": False,
                 "target_host": "x", "target_port": 4242},
                {"kind": "tcp_client", "name": "NoHost", "enabled": True,
                 "target_host": "", "target_port": 4242},
                {"kind": "auto", "name": "LAN", "enabled": True},
            ]
        )
    )
    assert "Off" not in text and "NoHost" not in text
    assert "AutoInterface" in text


def test_backbone_gateway_public_rate_preset():
    text = render_config(
        _settings(
            interfaces=[
                {
                    "kind": "backbone_server",
                    "name": "Public Gateway",
                    "enabled": True,
                    "listen_ip": "0.0.0.0",
                    "port": 4242,
                    "gateway_mode": True,
                }
            ]
        )
    )
    assert "type = BackboneInterface" in text
    assert "mode = gateway" in text
    for key in ("announce_rate_target", "announce_rate_penalty", "announce_rate_grace"):
        assert key in text


def test_loopback_server_gets_no_rate_preset():
    text = render_config(
        _settings(
            interfaces=[
                {"kind": "tcp_server", "name": "Local", "enabled": True,
                 "listen_ip": "127.0.0.1", "port": 4242}
            ]
        )
    )
    assert "announce_rate_target" not in text


def test_validate_interfaces_catches_problems():
    problems = validate_interfaces(
        [
            {"kind": "bogus"},
            {"kind": "tcp_server", "name": "badport", "port": 99999},
            {"kind": "tcp_client", "name": "nohost", "target_port": 4242},
            {"kind": "tcp_client", "name": "ok", "target_host": "h", "target_port": 4242},
        ]
    )
    assert len(problems) == 3
    assert any("unknown kind" in p for p in problems)
    assert any("badport" in p for p in problems)
    assert any("target_host" in p for p in problems)


def test_duplicate_subsection_names_are_caught_by_preflight(tmp_path):
    """If extra_config_text collides with a structured interface name, config
    must fail validation cleanly (no silent RNS hard-exit)."""
    import pytest

    from meshdeck.rns.stack import InvalidConfigError, validate_interface_config

    text = render_config(
        _settings(
            interfaces=[
                {"kind": "tcp_server", "name": "Srv", "enabled": True,
                 "listen_ip": "127.0.0.1", "port": 4243}
            ],
            extra_config_text="  [[Srv]]\n    type = TCPServerInterface\n    enabled = yes\n"
                              "    listen_ip = 127.0.0.1\n    port = 4343",
        )
    )
    cfg = tmp_path / "config"
    cfg.write_text(text)
    with pytest.raises(InvalidConfigError):
        validate_interface_config(cfg)


def test_extra_config_text_still_appended_with_structured_interfaces():
    text = render_config(
        _settings(
            interfaces=[{"kind": "auto", "name": "LAN", "enabled": True}],
            extra_config_text="[reticulum]\n  enable_transport = Yes",
        )
    )
    # merged into the [reticulum] section, not appended as a duplicate section
    assert text.count("[reticulum]") == 1
    assert "enable_transport = Yes" in text
