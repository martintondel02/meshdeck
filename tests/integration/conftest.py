# Integration tests spawn real RNS/LXMF subprocesses; keep them out of unit runs.
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: spawns real network subprocesses")
