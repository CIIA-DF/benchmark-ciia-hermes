"""I3: real proxy route, transport faults and bounded bodies with synthetic peers."""

import shutil
import subprocess
from pathlib import Path

import pytest

from agents.interface import ModelConfig

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "tests/integration/i3_proxy_probe.cjs"


@pytest.mark.skipif(
    not shutil.which("node")
    or not (ROOT / "portal/node_modules/next/server.js").exists()
    or not (ROOT / "portal/node_modules/typescript").is_dir(),
    reason="Proxy I3 requer Node e dependências do portal instaladas com npm ci.",
)
@pytest.mark.parametrize(
    "scenario",
    [
        "chunk_body",
        "body_timeout",
        "declared_size",
        "exact_limit",
        "wire_sse",
        "header_timeout",
        "idle_timeout",
        "disconnect",
        "request_abort",
        "status_headers",
        "blank_timeout",
        "guards",
        "configuration",
        "upstream_failure",
    ],
)
def test_actual_proxy_route_with_synthetic_transport(scenario):
    result = subprocess.run(
        ["node", str(PROBE), scenario, str(ROOT)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("timeout", ["nan", "inf", "-inf", "0", "-1"])
def test_model_timeout_must_be_positive_and_finite(monkeypatch, timeout):
    for name, value in {
        "LLM_BASE_URL": "http://synthetic.invalid",
        "LLM_MODEL": "synthetic",
        "LLM_API_KEY": "synthetic-private-key",
        "LLM_TIMEOUT_SECONDS": timeout,
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        ModelConfig.from_environment()


def test_nginx_profile_matches_body_limit_and_stream_transport_contract():
    config = (ROOT / "infra/nginx-chat.conf").read_text(encoding="utf-8")
    assert "client_max_body_size 1m;" in config
    location = config.split("location /api/chat/ {", 1)[1].split("}", 1)[0]
    for directive in [
        "proxy_buffering off;",
        "proxy_cache off;",
        "proxy_http_version 1.1;",
        'proxy_set_header Connection "";',
        "proxy_connect_timeout 5s;",
        "proxy_send_timeout 30s;",
        "proxy_read_timeout 360s;",
        "proxy_set_header Host $http_host;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
    ]:
        assert directive in location
