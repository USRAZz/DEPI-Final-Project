"""ops/monitor/check_health.py against stub services on random ports (no Docker needed)."""
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops" / "monitor"))
import check_health  # noqa: E402


def _stub(status: int, body: dict):
    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def stubs():
    servers = []

    def make(status=200, body=None):
        s = _stub(status, {"status": "ok"} if body is None else body)
        servers.append(s)
        return f"http://127.0.0.1:{s.server_port}"
    yield make
    for s in servers:
        s.shutdown()


def test_all_up_exits_0(stubs, capsys):
    assert check_health.main(["--url", f"api={stubs()}/health", "--url", f"risk={stubs()}/health"]) == 0
    assert "ALL OK" in capsys.readouterr().out


@pytest.mark.parametrize("status,body,detail", [(503, {"status": "ok"}, "HTTP 503"),
                                                (200, {"status": "degraded"}, "status='degraded'")])
def test_unhealthy_answer_fails(stubs, capsys, status, body, detail):
    assert check_health.main(["--url", f"api={stubs(status, body)}/health"]) == 1
    assert detail in capsys.readouterr().out


def test_nothing_listening_fails(capsys):
    assert check_health.main(["--url", "api=http://127.0.0.1:9/health", "--timeout", "1"]) == 1
    assert "FAIL  health:api" in capsys.readouterr().out


def test_broken_audit_chain_fails(stubs, capsys, monkeypatch):
    monkeypatch.setenv("AUDIT_VERIFY_TOKEN", "t")
    gw = stubs(200, {"status": "ok", "ok": False, "first_broken_id": 7})
    assert check_health.main(["--url", f"gateway={gw}/health", "--audit-companies", "1"]) == 1
    out = capsys.readouterr().out
    assert "chain BROKEN at entry id 7" in out


def test_audit_requested_without_token_fails(stubs, capsys, monkeypatch):
    monkeypatch.delenv("AUDIT_VERIFY_TOKEN", raising=False)
    assert check_health.main(["--url", f"gateway={stubs()}/health", "--audit-companies", "1"]) == 1
    assert "AUDIT_VERIFY_TOKEN is not set" in capsys.readouterr().out
