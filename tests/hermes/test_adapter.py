import json
from uuid import uuid4

import httpx
import pytest

from agents.hermes.adapter import SYSTEM_PROMPT, HermesAdapter
from agents.interface import ModelConfig, ToolClient
from contracts.models import ExperimentRun, ToolContext


def _mock_openai_client(monkeypatch, responses, mock_model_config=True):
    requests = []
    tool_requests = []
    llm_headers = []
    tool_client_urls = []

    class MockClient:
        def __init__(self, **kwargs):
            self.default_headers = kwargs.get("headers", {})

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            if len(exc_info) != 3:
                raise AssertionError("Context manager recebeu argumentos de saída inválidos.")
            return False

        def post(self, url, **kwargs):
            if "/tools/" in url:
                tool_requests.append((url, kwargs["json"]))
                payload = {"process": {"title": "Processo sintético"}}
            else:
                requests.append(kwargs["json"])
                llm_headers.append({**self.default_headers, **kwargs["headers"]})
                payload = responses.pop(0)
            request = httpx.Request("POST", f"http://test{url}")
            return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr("agents.hermes.adapter.httpx.Client", MockClient)
    if mock_model_config:
        monkeypatch.setattr(
            "agents.hermes.adapter._model_config_from_environment",
            lambda: ModelConfig(
                base_url="http://llm.test/v1",
                model="model-test",
                api_key="test-key",
                timeout_seconds=5,
            ),
        )

    def create_tool_client(base_url):
        tool_client_urls.append(base_url)
        return ToolClient(base_url)

    monkeypatch.setattr("agents.hermes.adapter.ToolClient", create_tool_client)
    return requests, tool_requests, llm_headers, tool_client_urls


def _context():
    return ToolContext(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )


def test_hermes_system_prompt_requires_sei_evidence_rules():
    assert "ler_documento" in SYSTEM_PROMPT
    assert "fato, data ou avaliação de conformidade" in SYSTEM_PROMPT
    assert "ID exato" in SYSTEM_PROMPT
    assert "página física" in SYSTEM_PROMPT
    assert "[DOC-DEMO-001, página 2]" in SYSTEM_PROMPT
    assert "items vazia" in SYSTEM_PROMPT
    assert "não prova" in SYSTEM_PROMPT
    assert "não conclua pela ausência no SEI original" in SYSTEM_PROMPT


def test_hermes_adapter_exposes_required_run_signature():
    assert HermesAdapter.run.__annotations__ == {
        "task": str,
        "context": ToolContext,
        "return": ExperimentRun,
    }


def test_hermes_adapter_runs_tool_calls_and_records_usage(monkeypatch):
    context = _context()
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "consultar_processo",
                                    "arguments": context.model_dump_json(),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Consulta concluída."}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8},
        },
    ]
    requests, tool_requests, llm_headers, tool_client_urls = _mock_openai_client(
        monkeypatch, responses
    )

    adapter = HermesAdapter()
    result = adapter.run("Consulte o processo.", context)

    assert isinstance(result, ExperimentRun)
    assert result.executor == "hermes"
    assert result.model == "model-test"
    assert result.run_id == context.run_id
    assert result.latency_ms >= 0
    assert result.input_tokens == 32
    assert result.output_tokens == 11
    assert result.agent_declared_success is True
    assert adapter.final_response == "Consulta concluída."
    assert llm_headers[0]["Authorization"] == "Bearer test-key"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool == "consultar_processo"
    assert result.tool_calls[0].status == "ok"
    assert tool_requests[0][0] == "/tools/consultar_processo"
    assert tool_requests[0][1] == context.model_dump(mode="json")
    assert requests[0]["tools"]
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert requests[1]["messages"][-1]["tool_call_id"] == "call-1"
    assert tool_client_urls == ["http://127.0.0.1:8000"]


def test_hermes_adapter_reports_invalid_tool_arguments_and_continues(monkeypatch):
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-invalid-json",
                                "type": "function",
                                "function": {
                                    "name": "consultar_processo",
                                    "arguments": '{"run_id":',
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {"choices": [{"message": {"role": "assistant", "content": "A chamada falhou."}}]},
    ]
    requests, tool_requests, _, _ = _mock_openai_client(monkeypatch, responses)

    adapter = HermesAdapter()
    result = adapter.run("Consulte o processo.", _context())

    assert len(requests) == 2
    assert tool_requests == []
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert requests[1]["messages"][-1]["tool_call_id"] == "call-invalid-json"
    assert "error" in json.loads(requests[1]["messages"][-1]["content"])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].status == "error"
    assert adapter.final_response == "A chamada falhou."


@pytest.mark.parametrize(
    "tool_calls",
    [
        "",
        0,
        {},
        "malformed",
        [{"type": "function"}],
    ],
)
def test_hermes_adapter_retries_malformed_tool_call_envelope(monkeypatch, tool_calls):
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls,
                    }
                }
            ]
        },
        {"choices": [{"message": {"role": "assistant", "content": "Não foi possível consultar."}}]},
    ]
    requests, tool_requests, _, _ = _mock_openai_client(monkeypatch, responses)

    result = HermesAdapter().run("Consulte o processo.", _context())

    assert len(requests) == 2
    assert requests[1]["messages"][-1]["role"] == "user"
    assert all(message["role"] != "assistant" for message in requests[1]["messages"])
    assert tool_requests == []
    assert result.tool_calls == []


def test_hermes_adapter_accepts_openrouter_environment_and_optional_headers(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.test")
    monkeypatch.setenv("OPENROUTER_TITLE", "CIIA Hermes test")
    monkeypatch.setenv("BACKEND_URL", "http://backend.test:8000")
    responses = [{"choices": [{"message": {"role": "assistant", "content": "Concluído."}}]}]
    requests, _, llm_headers, tool_client_urls = _mock_openai_client(
        monkeypatch,
        responses,
        mock_model_config=False,
    )

    result = HermesAdapter().run("Tarefa sintética.", _context())

    assert result.model == "openai/gpt-4o-mini"
    assert len(requests) == 1
    assert llm_headers[0]["Authorization"] == "Bearer test-openrouter-key"
    assert llm_headers[0]["HTTP-Referer"] == "https://example.test"
    assert llm_headers[0]["X-OpenRouter-Title"] == "CIIA Hermes test"
    assert tool_client_urls == ["http://backend.test:8000"]
