"""Adaptador Hermes com loop ReAct sobre a API OpenAI-compatible."""

import hashlib
import importlib
import ipaddress
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from agents.hermes.tools import TOOLS, catalog_version, hermes_tool_schemas, inject_tool_context
from agents.interface import AgentAdapter, ModelConfig, ToolClient
from contracts.models import ExperimentRun, ToolCallRecord, ToolContext

SYSTEM_PROMPT = (
    "Responda às tarefas sobre processos SEI usando as ferramentas disponíveis. "
    "Antes de apresentar qualquer fato, data ou avaliação de conformidade sobre o processo, "
    "leia o documento relevante na íntegra com ler_documento; resultados de busca servem "
    "apenas para localizar documentos e não bastam como evidência. "
    "Fundamente toda afirmação factual extraída de um documento com seu ID exato e o número "
    "da página física retornado pela leitura, por exemplo: [DOC-DEMO-001, página 2]. "
    "Não invente fatos, datas ou conformidades. Se não leu o documento ou não encontrou "
    "nele evidência suficiente, não apresente a afirmação como fato e explicite a limitação. "
    "Se buscar_documentos retornar uma lista items vazia, informe que nenhum trecho "
    "correspondente foi localizado na base consultada e que isso não prova que o documento "
    "não exista no processo SEI original; não conclua pela ausência no SEI original."
)
MAX_TOOL_ROUNDS = 10
PROJECT_VERSION = "0.1.0"
MODEL_TEMPERATURE = 0.0
MODEL_SEED = 42
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
TASKS_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "tasks.json"

# Preços por 1 milhão de tokens (prompt_usd, completion_usd) conforme ADR 003.
TOKEN_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "meta-llama/llama-3.1-70b-instruct": (0.35, 0.40),
    "meta-llama/llama-3.3-70b-instruct": (0.35, 0.40),
    "meta-llama/llama-3.3-70b-instruct:free": (0.0, 0.0),
    "deepseek/deepseek-chat": (0.14, 0.28),
    "qwen/qwen-2.5-72b-instruct": (0.35, 0.40),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
}

# Códigos de erro definitivos do backend que encerram a execução (não corrigíveis pelo LLM).
_DEFINITIVE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "unauthorized",
        "forbidden",
        "version_mismatch",
        "budget_exceeded",
        "run_expired",
    }
)

# Falhas de transporte anteriores ao envio ao servidor (P10 — unobserved_tool_calls).
_NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


@dataclass(frozen=True)
class HermesRunResult:
    """Resultado consolidado contendo texto final e registro ExperimentRun."""

    response: str
    experiment_run: ExperimentRun


class HermesAdapter(AgentAdapter):
    def __init__(
        self,
        tool_client: Any | None = None,
        *,
        sink: Any | None = None,
        execution: Any | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ):
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds deve ser pelo menos 1.")
        self.tool_client = tool_client
        self.sink = sink
        self.execution = execution
        self.system_prompt = system_prompt
        self.max_tool_rounds = max_tool_rounds
        self.final_response = ""

    def run_with_result(
        self,
        task: str,
        context: ToolContext,
        *,
        task_id: str | None = None,
        split: Literal["development", "final"] = "development",
        repetition: int = 1,
    ) -> HermesRunResult:
        """Executa a tarefa e devolve par estruturado (response, experiment_run)."""
        experiment_run = self.run(
            task,
            context,
            task_id=task_id,
            split=split,
            repetition=repetition,
        )
        return HermesRunResult(response=self.final_response, experiment_run=experiment_run)

    def run(
        self,
        task: str,
        context: ToolContext,
        *,
        task_id: str | None = None,
        split: Literal["development", "final"] = "development",
        repetition: int = 1,
    ) -> ExperimentRun:
        self.final_response = ""
        config = _model_config_from_environment()
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        active_tools = hermes_tool_schemas() if TOOLS == hermes_tool_schemas() else TOOLS
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task},
        ]
        backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        tool_client = self.tool_client if self.tool_client is not None else ToolClient(backend_url)
        tool_calls: list[ToolCallRecord] = []
        local_unobserved_calls = 0
        persisted_artifact_ids: list[str] = []
        input_tokens = 0
        output_tokens = 0
        input_tokens_known = True
        output_tokens_known = True
        final_content = ""

        with httpx.Client(
            timeout=config.timeout_seconds,
            headers=_model_headers(config),
        ) as client:
            for round_number in range(self.max_tool_rounds + 1):
                response = client.post(
                    f"{config.base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": config.model,
                        "messages": messages,
                        "tools": active_tools,
                        "tool_choice": "auto",
                        "temperature": MODEL_TEMPERATURE,
                        "seed": MODEL_SEED,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                choice = _first_choice(payload)
                message = choice.get("message")
                if not isinstance(message, dict):
                    raise ValueError("Resposta da LLM sem mensagem válida.")

                usage = payload.get("usage")
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens")
                    completion_tokens = usage.get("completion_tokens")
                    if isinstance(prompt_tokens, int):
                        input_tokens += prompt_tokens
                    else:
                        input_tokens_known = False
                    if isinstance(completion_tokens, int):
                        output_tokens += completion_tokens
                    else:
                        output_tokens_known = False
                else:
                    input_tokens_known = False
                    output_tokens_known = False

                calls = message.get("tool_calls", [])
                if calls is None:
                    calls = []
                if not isinstance(calls, list):
                    _request_valid_tool_calls(messages, round_number, self.max_tool_rounds)
                    continue
                if not calls:
                    content = message.get("content")
                    final_content = content if isinstance(content, str) else ""
                    break
                if round_number == self.max_tool_rounds:
                    raise RuntimeError("Limite de rodadas de ferramentas do Hermes excedido.")

                identities: list[tuple[str, str]] = []
                for call in calls:
                    identity = _tool_call_identity(call)
                    if identity is None:
                        break
                    identities.append(identity)
                if len(identities) != len(calls):
                    _request_valid_tool_calls(messages, round_number, self.max_tool_rounds)
                    continue

                messages.append(message)
                for call, identity in zip(calls, identities, strict=True):
                    tool_call_id, name = identity
                    tool_started = time.perf_counter()
                    observed_by_server = True
                    try:
                        _, _, arguments = _parse_tool_call(call)
                    except ValueError:
                        result = {
                            "error": {
                                "code": "invalid_arguments",
                                "message": (
                                    "Argumentos inválidos: envie um objeto JSON válido "
                                    "para a ferramenta."
                                ),
                            }
                        }
                        status = "error"
                        artifact_id = None
                    else:
                        merged_arguments = inject_tool_context(arguments, context)
                        artifact_id = None
                        try:
                            raw_result = tool_client.call(name, merged_arguments)
                            if (
                                isinstance(raw_result, dict)
                                and "code" in raw_result
                                and "message" in raw_result
                                and "error" not in raw_result
                            ):
                                err_code = raw_result["code"]
                                if err_code in _DEFINITIVE_ERROR_CODES:
                                    raise RuntimeError(
                                        f"Erro definitivo da ferramenta {name}: {err_code}"
                                    )
                                result = {
                                    "error": {
                                        "code": err_code,
                                        "message": raw_result["message"],
                                    }
                                }
                                status = "error"
                            elif isinstance(raw_result, dict) and "error" in raw_result:
                                err_obj = raw_result["error"]
                                err_code = (
                                    err_obj.get("code") if isinstance(err_obj, dict) else None
                                )
                                if err_code in _DEFINITIVE_ERROR_CODES:
                                    raise RuntimeError(
                                        f"Erro definitivo da ferramenta {name}: {err_code}"
                                    )
                                result = raw_result
                                status = "error"
                            else:
                                result = raw_result
                                status = "ok"
                                if (
                                    isinstance(result, dict)
                                    and "artifact_id" in result
                                    and isinstance(result["artifact_id"], str)
                                ):
                                    artifact_id = result["artifact_id"]
                                    persisted_artifact_ids.append(artifact_id)
                        except httpx.HTTPStatusError as exc:
                            if _is_definitive_http_error(exc):
                                raise
                            status = "error"
                            result = _extract_http_error_envelope(exc)
                        except _NOT_SENT_ERRORS as exc:
                            # P10: falha antes do envio não chega ao servidor e vira contagem em
                            # parameters["unobserved_tool_calls"], ficando fora de tool_calls.
                            observed_by_server = False
                            if not hasattr(tool_client, "unobserved"):
                                local_unobserved_calls += 1
                            status = "error"
                            result = {
                                "error": {
                                    "code": "backend_unavailable",
                                    "message": f"Falha de comunicação com o backend: {exc}",
                                }
                            }
                        except httpx.HTTPError as exc:
                            status = "error"
                            result = {
                                "error": {
                                    "code": "backend_unavailable",
                                    "message": f"Falha de comunicação com o backend: {exc}",
                                }
                            }
                        except ValueError as exc:
                            status = "error"
                            result = {
                                "error": {
                                    "code": "invalid_tool_call",
                                    "message": str(exc),
                                }
                            }
                    duration_ms = (time.perf_counter() - tool_started) * 1000
                    if observed_by_server:
                        tool_calls.append(
                            ToolCallRecord(
                                tool_call_id=tool_call_id,
                                tool=name,
                                duration_ms=duration_ms,
                                status=status,
                                artifact_id=artifact_id,
                            )
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            else:
                raise RuntimeError("Loop ReAct do Hermes terminou sem resposta final.")

        self.final_response = final_content
        prompt_hash = hashlib.sha256(
            json.dumps(
                {"system": self.system_prompt, "task": task, "tools": active_tools},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        resolved_task_id, resolved_split, resolved_repetition = _resolve_execution_metadata(
            self.execution,
            task,
            context,
            task_id,
            split,
            repetition,
        )
        endpoint_id = f"endpoint-{hashlib.sha256(config.base_url.encode()).hexdigest()[:16]}"

        client_calls = getattr(tool_client, "calls", None)
        if isinstance(client_calls, list) and client_calls:
            recorded_tool_calls = list(client_calls)
            recorded_artifacts = list(
                dict.fromkeys(
                    c.artifact_id for c in recorded_tool_calls if c.artifact_id is not None
                )
            )
        else:
            recorded_tool_calls = tool_calls
            recorded_artifacts = persisted_artifact_ids

        client_unobserved = getattr(tool_client, "unobserved", None)
        unobserved_count = (
            len(client_unobserved) if isinstance(client_unobserved, list) else 0
        ) + local_unobserved_calls

        experiment_run = ExperimentRun(
            **context.model_dump(exclude={"task_id"}),
            task_id=resolved_task_id,
            split=resolved_split,
            executor="hermes",
            repetition=resolved_repetition,
            code_commit=_git_commit(),
            harness_version=PROJECT_VERSION,
            adapter_version=PROJECT_VERSION,
            model=config.model,
            endpoint_id=endpoint_id,
            prompt_sha256=prompt_hash,
            parameters={
                "max_tool_rounds": self.max_tool_rounds,
                "temperature": MODEL_TEMPERATURE,
                "seed": MODEL_SEED,
                "final_response": final_content,
                "catalog_version": catalog_version(),
                "unobserved_tool_calls": unobserved_count,
            },
            started_at=started_at,
            latency_ms=(time.perf_counter() - started) * 1000,
            tool_calls=recorded_tool_calls,
            input_tokens=input_tokens if input_tokens_known else None,
            output_tokens=output_tokens if output_tokens_known else None,
            cost_usd=_calculate_cost_usd(
                config.model,
                config.base_url,
                input_tokens if input_tokens_known else None,
                output_tokens if output_tokens_known else None,
            ),
            agent_declared_success=bool(final_content.strip()),
            persisted_artifact_ids=recorded_artifacts,
            verified_success=None,
            evaluator=None,
        )

        if self.sink is not None:
            existing = (
                self.sink.get(experiment_run.run_id)
                if callable(getattr(self.sink, "get", None))
                else None
            )
            if existing is not None and callable(getattr(self.sink, "update", None)):
                experiment_run = self.sink.update(experiment_run)
            elif callable(getattr(self.sink, "save", None)):
                experiment_run = self.sink.save(experiment_run)

        return experiment_run


def create_adapter(
    tool_client: Any | None = None,
    sink: Any | None = None,
    execution: Any | None = None,
) -> HermesAdapter:
    """Instancia HermesAdapter com cliente, sink e execução injetados pelo worker."""
    return HermesAdapter(tool_client=tool_client, sink=sink, execution=execution)


def adapter(*, use_sink: bool = False) -> Any:
    """Fábrica sem argumentos compatível com `python -m agents.worker --executor hermes`."""
    try:
        compat = importlib.import_module("agents.compat")
        run_bridge_cls = getattr(compat, "RunBridge", None)
        if callable(run_bridge_cls):
            if use_sink:
                return run_bridge_cls(
                    lambda tools, sink, execution: create_adapter(
                        tool_client=tools,
                        sink=sink,
                        execution=execution,
                    )
                )
            return run_bridge_cls(
                lambda tools, execution: create_adapter(
                    tool_client=tools,
                    execution=execution,
                )
            )
    except ImportError:
        pass
    return HermesAdapter()


def _resolve_execution_metadata(
    execution: Any | None,
    task: str,
    context: ToolContext,
    task_id: str | None,
    split: Literal["development", "final"],
    repetition: int,
) -> tuple[str, Literal["development", "final"], int]:
    task_meta = getattr(execution, "task_metadata", None)
    if not isinstance(task_meta, dict):
        task_meta = {}

    effective_task_id = task_id
    if effective_task_id is None and isinstance(task_meta.get("task_id"), str):
        candidate = task_meta["task_id"].strip()
        if candidate:
            effective_task_id = candidate

    resolved_task_id = _resolve_task_id(task, context, effective_task_id)

    resolved_split: Literal["development", "final"] = split
    if split == "development" and task_meta.get("split") in ("development", "final"):
        resolved_split = task_meta["split"]

    resolved_repetition = repetition
    meta_rep = task_meta.get("repetition")
    if repetition == 1 and isinstance(meta_rep, int) and not isinstance(meta_rep, bool):
        if meta_rep >= 1:
            resolved_repetition = meta_rep

    return resolved_task_id, resolved_split, resolved_repetition


def _is_definitive_http_error(exc: httpx.HTTPStatusError) -> bool:
    if exc.__class__.__name__ == "ToolCallError" or hasattr(exc, "error"):
        return True
    response = getattr(exc, "response", None)
    if response is None:
        return False
    if response.status_code in {401, 403}:
        return True
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("code") in _DEFINITIVE_ERROR_CODES:
            return True
    except Exception:
        pass
    return False


def _extract_http_error_envelope(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    try:
        error_payload = exc.response.json()
        if isinstance(error_payload, dict):
            code = error_payload.get("code") or f"http_{exc.response.status_code}"
            message = (
                error_payload.get("message")
                or exc.response.text
                or "A chamada da ferramenta falhou."
            )
            return {"error": {"code": code, "message": message}}
    except Exception:
        pass
    return {
        "error": {
            "code": f"http_{exc.response.status_code}",
            "message": exc.response.text or "A chamada da ferramenta falhou.",
        }
    }


def _resolve_task_id(task: str, context: ToolContext, task_id: str | None) -> str:
    if task_id is not None:
        return task_id

    context_task_id = getattr(context, "task_id", None)
    if context_task_id is not None:
        return context_task_id

    if TASKS_PATH.exists():
        with TASKS_PATH.open(encoding="utf-8") as tasks_file:
            tasks = json.load(tasks_file)
        if not isinstance(tasks, list):
            raise ValueError(f"O arquivo {TASKS_PATH} deve conter uma lista de tarefas.")

        matching_ids = [
            item["task_id"]
            for item in tasks
            if isinstance(item, dict)
            and item.get("prompt") == task
            and isinstance(item.get("task_id"), str)
            and item["task_id"]
        ]
        if len(matching_ids) > 1:
            raise ValueError(f"Mais de uma tarefa corresponde ao prompt em {TASKS_PATH}.")
        if matching_ids:
            return matching_ids[0]

    return f"task-{hashlib.sha256(task.encode('utf-8')).hexdigest()[:16]}"


def _calculate_cost_usd(
    model: str,
    base_url: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    hostname = urlsplit(base_url).hostname
    if hostname is not None and _is_loopback_host(hostname):
        return 0.0

    if model.endswith(":free"):
        return 0.0

    prices = TOKEN_PRICES_PER_MILLION.get(model)
    if prices is None or input_tokens is None or output_tokens is None:
        return None

    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def _is_loopback_host(hostname: str) -> bool:
    if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _git_commit() -> str:
    commit = os.getenv("GIT_COMMIT")
    if commit:
        return commit
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _model_config_from_environment() -> ModelConfig:
    if os.getenv("LLM_API_KEY"):
        return ModelConfig.from_environment()

    base_url = os.getenv("LLM_BASE_URL", "")
    model = os.getenv("LLM_MODEL", "")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not all((base_url, model, api_key)):
        raise ValueError("Configure LLM_BASE_URL, LLM_MODEL e LLM_API_KEY ou OPENROUTER_API_KEY.")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    if timeout <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS deve ser positivo.")
    return ModelConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout,
    )


def _model_headers(config: ModelConfig) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {config.api_key}"}
    optional_headers = {
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER"),
        "X-OpenRouter-Title": os.getenv("OPENROUTER_TITLE"),
    }
    headers.update({name: value for name, value in optional_headers.items() if value})
    return headers


def _first_choice(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Resposta da LLM deve ser um objeto JSON.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Resposta da LLM sem choices válidas.")
    return choices[0]


def _tool_call_identity(call: object) -> tuple[str, str] | None:
    if not isinstance(call, dict) or call.get("type") != "function":
        return None
    function = call.get("function")
    if not isinstance(function, dict):
        return None
    call_id = call.get("id")
    name = function.get("name")
    if (
        not isinstance(call_id, str)
        or not _IDENTIFIER_PATTERN.fullmatch(call_id)
        or not isinstance(name, str)
        or not _IDENTIFIER_PATTERN.fullmatch(name)
    ):
        return None
    return call_id, name


def _request_valid_tool_calls(
    messages: list[dict],
    round_number: int,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
) -> None:
    if round_number == max_tool_rounds:
        raise RuntimeError("Limite de rodadas de ferramentas do Hermes excedido.")
    messages.append(
        {
            "role": "user",
            "content": (
                "A resposta anterior continha chamadas de ferramenta malformadas. "
                "Envie novamente as chamadas com ID, nome e formato válidos, sem "
                "apresentar um resultado como concluído."
            ),
        }
    )


def _parse_tool_call(call: object) -> tuple[str, str, dict]:
    if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
        raise ValueError("Resposta da LLM contém tool_call inválido.")
    call_id = call.get("id")
    function = call["function"]
    name = function["name"]
    raw_arguments = function.get("arguments")
    if not isinstance(call_id, str) or not isinstance(name, str):
        raise ValueError("Resposta da LLM contém ID ou nome de ferramenta inválido.")
    if isinstance(raw_arguments, str):
        arguments = json.loads(raw_arguments)
    else:
        arguments = raw_arguments
    if not isinstance(arguments, dict):
        raise ValueError("Argumentos da ferramenta devem ser um objeto JSON.")
    return call_id, name, arguments
