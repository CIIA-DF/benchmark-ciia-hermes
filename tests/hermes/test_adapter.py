import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

import httpx
import pytest

from agents.hermes.adapter import (
    SYSTEM_PROMPT,
    HermesAdapter,
    HermesRunResult,
    _calculate_cost_usd,
    _resolve_task_id,
    adapter,
    create_adapter,
)
from agents.hermes.tools import catalog_version, inject_tool_context
from agents.interface import ModelConfig, ToolClient
from contracts.models import ExperimentRun, ToolCallRecord, ToolContext


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
                assert "headers" not in kwargs
                requests.append(kwargs["json"])
                llm_headers.append(self.default_headers)
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
        "task_id": str | None,
        "split": Literal["development", "final"],
        "repetition": int,
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
    assert result.parameters == {
        "max_tool_rounds": 10,
        "temperature": 0.0,
        "seed": 42,
        "final_response": "Consulta concluída.",
        "catalog_version": catalog_version(),
        "unobserved_tool_calls": 0,
    }
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
    assert requests[0]["temperature"] == 0.0
    assert requests[0]["seed"] == 42


def test_hermes_adapter_uses_supplied_task_id(monkeypatch):
    responses = [{"choices": [{"message": {"role": "assistant", "content": "Concluído."}}]}]
    _mock_openai_client(monkeypatch, responses)

    result = HermesAdapter().run("Tarefa sintética.", _context(), task_id="DEV-001")

    assert result.task_id == "DEV-001"


def test_hermes_adapter_uses_supplied_parameters(monkeypatch):
    responses = [{"choices": [{"message": {"role": "assistant", "content": "Concluído."}}]}]
    _mock_openai_client(monkeypatch, responses)

    result = HermesAdapter().run(
        "Tarefa sintética.",
        _context(),
        task_id="CUSTOM-001",
        split="final",
        repetition=3,
    )

    assert result.task_id == "CUSTOM-001"
    assert result.split == "final"
    assert result.repetition == 3


def test_inject_tool_context_prevents_llm_override():
    authenticated = _context()
    malicious_arguments = {
        "run_id": str(uuid4()),
        "process_id": "PROC-EVIL-666",
        "corpus_version": "corrupted-corpus",
        "requirements_version": "fake-reqs",
        "query": "solicitação de diárias",
    }
    injected = inject_tool_context(malicious_arguments, authenticated)
    assert injected["run_id"] == str(authenticated.run_id)
    assert injected["process_id"] == authenticated.process_id
    assert injected["corpus_version"] == authenticated.corpus_version
    assert injected["requirements_version"] == authenticated.requirements_version
    assert injected["query"] == "solicitação de diárias"


def test_hermes_adapter_handles_backend_tool_error(monkeypatch):
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
                                "id": "call-err-1",
                                "type": "function",
                                "function": {
                                    "name": "consultar_requisitos",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 5},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "A ferramenta de requisitos não está implementada.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 25, "completion_tokens": 10},
        },
    ]

    requests = []

    class MockClient:
        def __init__(self, **kwargs):
            self.default_headers = kwargs.get("headers", {})

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def post(self, url, **kwargs):
            if "/tools/" in url:
                error_body = {
                    "code": "not_implemented",
                    "message": "Contrato previsto; ferramenta ainda não implementada.",
                    "run_id": str(context.run_id),
                    "retryable": False,
                }
                request = httpx.Request("POST", f"http://test{url}")
                return httpx.Response(501, json=error_body, request=request)
            requests.append(kwargs["json"])
            payload = responses.pop(0)
            request = httpx.Request("POST", f"http://test{url}")
            return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr("agents.hermes.adapter.httpx.Client", MockClient)
    monkeypatch.setattr(
        "agents.hermes.adapter._model_config_from_environment",
        lambda: ModelConfig(
            base_url="http://llm.test/v1",
            model="model-test",
            api_key="test-key",
            timeout_seconds=5,
        ),
    )

    adapter = HermesAdapter()
    result = adapter.run("Consulte os requisitos normativos.", context)

    assert result.agent_declared_success is True
    assert adapter.final_response == "A ferramenta de requisitos não está implementada."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool == "consultar_requisitos"
    assert result.tool_calls[0].status == "error"
    # Verifica que o erro retornado pelo backend foi propagado à LLM no envelope padrão
    tool_message = requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-err-1"
    tool_content = json.loads(tool_message["content"])
    assert tool_content["error"]["code"] == "not_implemented"
    assert "ferramenta ainda não implementada" in tool_content["error"]["message"]


def test_hermes_adapter_uses_task_id_from_context(monkeypatch, tmp_path):
    class ContextWithTaskId(ToolContext):
        task_id: str

    context = ContextWithTaskId(**_context().model_dump(), task_id="DEV-CONTEXT-001")
    monkeypatch.setattr("agents.hermes.adapter.TASKS_PATH", tmp_path / "missing.json")
    responses = [{"choices": [{"message": {"role": "assistant", "content": "Concluído."}}]}]
    _mock_openai_client(monkeypatch, responses)

    result = HermesAdapter().run("Tarefa sintética.", context)

    assert result.task_id == "DEV-CONTEXT-001"


def test_hermes_adapter_resolves_task_id_from_catalog_when_called_positionally(
    monkeypatch, tmp_path
):
    task_prompt = "Tarefa sintética do catálogo."
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps([{"task_id": "DEV-TEST-001", "prompt": task_prompt}]),
        encoding="utf-8",
    )
    monkeypatch.setattr("agents.hermes.adapter.TASKS_PATH", tasks_path)
    responses = [{"choices": [{"message": {"role": "assistant", "content": "Concluído."}}]}]
    _mock_openai_client(monkeypatch, responses)

    result = HermesAdapter().run(task_prompt, _context())

    assert result.task_id == "DEV-TEST-001"


def test_hermes_adapter_falls_back_to_hashed_task_id(monkeypatch, tmp_path):
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("agents.hermes.adapter.TASKS_PATH", tasks_path)
    task_prompt = "Tarefa sem ID no catálogo."

    result = _resolve_task_id(task_prompt, _context(), None)

    assert result == f"task-{hashlib.sha256(task_prompt.encode()).hexdigest()[:16]}"


@pytest.mark.parametrize(
    ("model", "base_url", "input_tokens", "output_tokens", "expected"),
    [
        ("gpt-4o-mini", "https://api.example.test/v1", 1_000, 2_000, 0.00135),
        ("openai/gpt-4o-mini", "https://api.example.test/v1", 1_000, 2_000, 0.00135),
        (
            "meta-llama/llama-3.1-70b-instruct",
            "https://api.example.test/v1",
            1_000_000,
            1_000_000,
            0.75,
        ),
        (
            "meta-llama/llama-3.3-70b-instruct",
            "https://api.example.test/v1",
            1_000_000,
            1_000_000,
            0.75,
        ),
        (
            "meta-llama/llama-3.3-70b-instruct:free",
            "https://api.example.test/v1",
            5_000,
            1_000,
            0.0,
        ),
        ("deepseek/deepseek-chat", "https://api.example.test/v1", 1_000_000, 1_000_000, 0.42),
        ("qwen/qwen-2.5-72b-instruct", "https://api.example.test/v1", 1_000_000, 1_000_000, 0.75),
        ("anthropic/claude-sonnet-4.5", "https://api.example.test/v1", 10_000, 2_000, 0.06),
        ("anthropic/claude-sonnet-4.6", "https://api.example.test/v1", 10_000, 2_000, 0.06),
        ("hermes3:8b", "http://localhost:11434/v1", None, None, 0.0),
        ("unknown-model", "https://api.example.test/v1", 1, 1, None),
        ("gpt-4o-mini", "https://api.example.test/v1", None, 10, None),
    ],
)
def test_hermes_adapter_calculates_known_and_local_costs(
    model, base_url, input_tokens, output_tokens, expected
):
    assert _calculate_cost_usd(model, base_url, input_tokens, output_tokens) == expected


def test_hermes_adapter_records_cost_in_experiment_run(monkeypatch):
    responses = [
        {
            "choices": [{"message": {"role": "assistant", "content": "Concluído."}}],
            "usage": {"prompt_tokens": 1_000, "completion_tokens": 2_000},
        }
    ]
    _mock_openai_client(monkeypatch, responses)
    monkeypatch.setattr(
        "agents.hermes.adapter._model_config_from_environment",
        lambda: ModelConfig(
            base_url="https://api.example.test/v1",
            model="gpt-4o-mini",
            api_key="test-key",
            timeout_seconds=5,
        ),
    )

    result = HermesAdapter().run("Tarefa sintética.", _context(), task_id="DEV-001")

    assert result.cost_usd == 0.00135


def test_hermes_adapter_uses_git_commit_when_environment_is_unset(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(
        "agents.hermes.adapter.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="abc123\n"),
    )
    responses = [{"choices": [{"message": {"role": "assistant", "content": "Concluído."}}]}]
    _mock_openai_client(monkeypatch, responses)

    result = HermesAdapter().run("Tarefa sintética.", _context())

    assert result.code_commit == "abc123"


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

    monkeypatch.setenv("LLM_API_KEY", "test-key")
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


def test_hermes_adapter_accepts_injected_tool_client_and_execution_metadata(monkeypatch):
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
                                "id": "call-bridge-1",
                                "type": "function",
                                "function": {
                                    "name": "consultar_processo",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Processo conferido."}}],
            "usage": {"prompt_tokens": 18, "completion_tokens": 6},
        },
    ]
    _mock_openai_client(monkeypatch, responses)

    class InjectedSyncToolClient:
        def __init__(self):
            self.calls = []
            self.unobserved = [
                ToolCallRecord(
                    tool_call_id="unobs-1",
                    tool="ler_documento",
                    duration_ms=5.0,
                    status="error",
                )
            ]

        def call(self, name, arguments):
            self.calls.append(
                ToolCallRecord(
                    tool_call_id="server-id-1",
                    tool=name,
                    duration_ms=11.0,
                    status="ok",
                    artifact_id="art-123",
                )
            )
            return {"process": {"title": "Processo via RunBridge"}, "artifact_id": "art-123"}

    execution = SimpleNamespace(
        task_metadata={
            "task_id": "DEV-012",
            "split": "final",
            "repetition": 4,
        }
    )
    injected_client = InjectedSyncToolClient()
    hermes = HermesAdapter(tool_client=injected_client, execution=execution)
    result = hermes.run("Tarefa reservada pelo worker.", context)

    assert result.task_id == "DEV-012"
    assert result.split == "final"
    assert result.repetition == 4
    assert [c.tool_call_id for c in result.tool_calls] == ["server-id-1"]
    assert result.persisted_artifact_ids == ["art-123"]
    assert result.parameters["unobserved_tool_calls"] == 1
    assert result.parameters["catalog_version"] == catalog_version()


def test_hermes_adapter_run_with_result_and_sink_persistence(monkeypatch):
    context = _context()
    responses = [
        {"choices": [{"message": {"role": "assistant", "content": "Primeira execução."}}]},
        {"choices": [{"message": {"role": "assistant", "content": "Segunda execução."}}]},
    ]
    _mock_openai_client(monkeypatch, responses)

    class FakeSink:
        def __init__(self):
            self.storage = {}
            self.saved_count = 0
            self.updated_count = 0

        def get(self, run_id):
            return self.storage.get(run_id)

        def save(self, run):
            self.saved_count += 1
            self.storage[run.run_id] = run
            return run

        def update(self, run):
            self.updated_count += 1
            self.storage[run.run_id] = run
            return run

    sink = FakeSink()
    hermes = create_adapter(sink=sink)

    first = hermes.run_with_result("Tarefa 1", context, task_id="DEV-001")
    assert isinstance(first, HermesRunResult)
    assert first.response == "Primeira execução."
    assert first.experiment_run.task_id == "DEV-001"
    assert sink.saved_count == 1
    assert sink.updated_count == 0

    second = hermes.run_with_result("Tarefa 1", context, task_id="DEV-001")
    assert second.response == "Segunda execução."
    assert sink.saved_count == 1
    assert sink.updated_count == 1


def test_hermes_adapter_factory_wraps_run_bridge_when_available(monkeypatch):
    captured = {}

    class FakeRunBridge:
        def __init__(self, factory):
            self.factory = factory
            captured["factory"] = factory

    fake_compat = SimpleNamespace(RunBridge=FakeRunBridge)
    monkeypatch.setattr("agents.hermes.adapter.importlib.import_module", lambda name: fake_compat)

    bridge_2arg = adapter(use_sink=False)
    assert isinstance(bridge_2arg, FakeRunBridge)
    inst_2arg = bridge_2arg.factory("tools-obj", "exec-obj")
    assert isinstance(inst_2arg, HermesAdapter)
    assert inst_2arg.tool_client == "tools-obj"
    assert inst_2arg.execution == "exec-obj"
    assert inst_2arg.sink is None

    bridge_3arg = adapter(use_sink=True)
    assert isinstance(bridge_3arg, FakeRunBridge)
    inst_3arg = bridge_3arg.factory("tools-obj", "sink-obj", "exec-obj")
    assert isinstance(inst_3arg, HermesAdapter)
    assert inst_3arg.tool_client == "tools-obj"
    assert inst_3arg.sink == "sink-obj"
    assert inst_3arg.execution == "exec-obj"


def test_hermes_adapter_propagates_definitive_tool_call_error_immediately(monkeypatch):
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
                                "id": "call-definitive",
                                "type": "function",
                                "function": {
                                    "name": "consultar_processo",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        }
    ]
    _mock_openai_client(monkeypatch, responses)

    class ToolCallError(httpx.HTTPStatusError):
        def __init__(self, response, error=None):
            super().__init__("Tool recusada", request=response.request, response=response)
            self.error = error

    class DefinitiveFailingClient:
        def call(self, name, arguments):
            req = httpx.Request("POST", f"http://test/tools/{name}")
            resp = httpx.Response(
                429,
                json={"code": "budget_exceeded", "message": "Orçamento de tools excedido."},
                request=req,
            )
            raise ToolCallError(resp, {"code": "budget_exceeded"})

    hermes = HermesAdapter(tool_client=DefinitiveFailingClient())
    with pytest.raises(ToolCallError):
        hermes.run("Consulte o processo.", context)


def test_hermes_adapter_tracks_unobserved_tool_calls_p10_when_connection_fails(monkeypatch):
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
                                "id": "call-conn-err",
                                "type": "function",
                                "function": {
                                    "name": "ler_documento",
                                    "arguments": '{"document_id": "DOC-DEMO-001"}',
                                },
                            },
                            {
                                "id": "call-read-timeout",
                                "type": "function",
                                "function": {
                                    "name": "consultar_processo",
                                    "arguments": "{}",
                                },
                            },
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Recuperado após falha transitória.",
                    }
                }
            ]
        },
    ]
    _mock_openai_client(monkeypatch, responses)

    class FlakyTransportClient:
        def call(self, name, arguments):
            req = httpx.Request("POST", f"http://test/tools/{name}")
            if name == "ler_documento":
                raise httpx.ConnectError("Queda antes do envio", request=req)
            raise httpx.ReadTimeout("Timeout após envio ao servidor", request=req)

    hermes = HermesAdapter(tool_client=FlakyTransportClient())
    result = hermes.run("Tente ler e consultar.", context, task_id="DEV-001")

    # P10: ConnectError não entra em tool_calls e incrementa unobserved_tool_calls;
    # ReadTimeout entra em tool_calls como error.
    assert [c.tool for c in result.tool_calls] == ["consultar_processo"]
    assert result.tool_calls[0].status == "error"
    assert result.parameters["unobserved_tool_calls"] == 1


def test_hermes_adapter_end_to_end_against_local_backend_app(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from pipelines.documents.ingest import chunk_document, load_fixture
    from services.backend.app import create_app
    from services.backend.storage import ingest, initialize, make_engine

    db_path = tmp_path / "e2e_hermes.db"
    engine = make_engine(f"sqlite:///{db_path}")
    initialize(engine)
    examples_dir = Path(__file__).resolve().parents[2] / "examples"
    process, document = load_fixture(examples_dir)
    ingest(engine, process, document, chunk_document(document))
    app = create_app(engine)

    class InProcessToolClient:
        def __init__(self, fastapi_app):
            self.http = TestClient(fastapi_app)

        def call(self, name, arguments):
            resp = self.http.post(f"/tools/{name}", json=arguments)
            resp.raise_for_status()
            return resp.json()

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-e2e-1",
                                "type": "function",
                                "function": {
                                    "name": "consultar_processo",
                                    "arguments": "{}",
                                },
                            },
                            {
                                "id": "call-e2e-2",
                                "type": "function",
                                "function": {
                                    "name": "buscar_documentos",
                                    "arguments": '{"query": "dezembro de 2026", "limit": 5}',
                                },
                            },
                            {
                                "id": "call-e2e-3",
                                "type": "function",
                                "function": {
                                    "name": "ler_documento",
                                    "arguments": '{"document_id": "DOC-DEMO-001"}',
                                },
                            },
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 40},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "A previsão de entrega do material didático é dezembro de 2026 "
                            "[DOC-DEMO-001, página 2]. A exportação do processo é parcial."
                        ),
                    }
                }
            ],
            "usage": {"prompt_tokens": 240, "completion_tokens": 35},
        },
    ]
    requests, _, _, _ = _mock_openai_client(monkeypatch, responses)

    context = ToolContext(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )
    hermes = HermesAdapter(tool_client=InProcessToolClient(app))
    prompt = (
        "Consulte a previsão de entrega do material didático e informe a fonte "
        "e o limite da exportação."
    )
    run_result = hermes.run_with_result(prompt, context)

    assert run_result.experiment_run.task_id == "DEV-001"
    assert run_result.experiment_run.agent_declared_success is True
    assert "[DOC-DEMO-001, página 2]" in run_result.response
    assert [c.tool for c in run_result.experiment_run.tool_calls] == [
        "consultar_processo",
        "buscar_documentos",
        "ler_documento",
    ]
    assert all(c.status == "ok" for c in run_result.experiment_run.tool_calls)
    assert run_result.experiment_run.input_tokens == 360
    assert run_result.experiment_run.output_tokens == 75
    # Confirma que o conteúdo real da página 2 do banco foi entregue à LLM
    tool_msgs = [m for m in requests[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 3
    assert "dezembro de 2026" in tool_msgs[2]["content"]
