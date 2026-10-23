from uuid import uuid4

import httpx

from agents.hermes.adapter import HermesAdapter
from contracts.models import ExperimentRun, ToolContext


def test_hermes_adapter_exposes_required_run_signature():
    assert HermesAdapter.run.__annotations__ == {
        "task": str,
        "context": ToolContext,
        "return": ExperimentRun,
    }


def test_hermes_adapter_runs_tool_calls_and_records_usage(monkeypatch):
    context = ToolContext(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )
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
    requests = []
    tool_requests = []

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            if "/tools/" in url:
                tool_requests.append((url, kwargs["json"]))
                payload = {"process": {"title": "Processo sintético"}}
            else:
                requests.append(kwargs["json"])
                payload = responses.pop(0)
            request = httpx.Request("POST", f"http://test{url}")
            return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr("agents.hermes.adapter.httpx.Client", MockClient)
    monkeypatch.setattr(
        "agents.hermes.adapter.ModelConfig.from_environment",
        lambda: type(
            "Config",
            (),
            {
                "base_url": "http://llm.test/v1",
                "model": "model-test",
                "api_key": "test-key",
                "timeout_seconds": 5,
            },
        )(),
    )

    result = HermesAdapter().run("Consulte o processo.", context)

    assert isinstance(result, ExperimentRun)
    assert result.executor == "hermes"
    assert result.model == "model-test"
    assert result.input_tokens == 32
    assert result.output_tokens == 11
    assert result.agent_declared_success is True
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool == "consultar_processo"
    assert result.tool_calls[0].status == "ok"
    assert tool_requests[0][0] == "/tools/consultar_processo"
    assert tool_requests[0][1] == context.model_dump(mode="json")
    assert requests[0]["tools"]
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert requests[1]["messages"][-1]["tool_call_id"] == "call-1"


def test_hermes_adapter_injects_context_and_uses_backend_url(monkeypatch):
    context = ToolContext(
        run_id=uuid4(),
        process_id="PROC-DEMO-002",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )
    # LLM omite os campos do ToolContext e envia apenas o parâmetro específico da ferramenta
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-inject",
                                "type": "function",
                                "function": {
                                    "name": "buscar_documentos",
                                    "arguments": '{"query": "despacho"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Busca realizada."}}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 5},
        },
    ]
    tool_requests = []
    received_base_urls = []

    class MockClient:
        def __init__(self, *args, **kwargs):
            if "base_url" in kwargs:
                received_base_urls.append(kwargs["base_url"])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            if "/tools/" in url:
                tool_requests.append((url, kwargs["json"]))
                payload = {"results": []}
            else:
                payload = responses.pop(0)
            request = httpx.Request("POST", f"http://test{url}")
            return httpx.Response(200, json=payload, request=request)

    monkeypatch.setenv("BACKEND_URL", "http://custom-backend:9000")
    monkeypatch.setattr("agents.hermes.adapter.httpx.Client", MockClient)
    monkeypatch.setattr("agents.interface.httpx.Client", MockClient)
    monkeypatch.setattr(
        "agents.hermes.adapter.ModelConfig.from_environment",
        lambda: type(
            "Config",
            (),
            {
                "base_url": "http://llm.test/v1",
                "model": "model-test",
                "api_key": "test-key",
                "timeout_seconds": 5,
            },
        )(),
    )

    result = HermesAdapter().run("Busque despacho.", context)

    assert result.agent_declared_success is True
    assert "http://custom-backend:9000" in received_base_urls
    assert len(tool_requests) == 1
    call_url, call_payload = tool_requests[0]
    assert call_url == "/tools/buscar_documentos"
    # Garante que os campos de contexto foram injetados e o parâmetro da LLM foi preservado
    expected_args = {**context.model_dump(mode="json"), "query": "despacho"}
    assert call_payload == expected_args
