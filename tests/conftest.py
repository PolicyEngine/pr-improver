import socket
import sys
from pathlib import Path

import pytest
import streamlit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# app.py reads its secrets at import time; tests never reach the network.
streamlit.secrets = {
    "ANTHROPIC_API_KEY": "test-key",
    "GITHUB_TOKEN": "test-token",
}


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)
