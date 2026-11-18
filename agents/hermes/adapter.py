"""Adaptador Hermes com loop ReAct sobre a API OpenAI-compatible."""

import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx

from agents.hermes.tools import TOOLS, inject_tool_context
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
TOKEN_PRICES_PER_MILLION = {
    "gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "meta-llama/llama-3.1-70b-instruct": (0.35, 0.40),
}


class HermesAdapter(AgentAdapter):
    def __init__(self):
        self.final_response = ""

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
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        tool_client = ToolClient(backend_url)
        tool_calls: list[ToolCallRecord] = []
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
            for round_number in range(MAX_TOOL_ROUNDS + 1):
                response = client.post(
                    f"{config.base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": config.model,
                        "messages": messages,
                        "tools": TOOLS,
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
                    _request_valid_tool_calls(messages, round_number)
                    continue
                if not calls:
                    content = message.get("content")
                    final_content = content if isinstance(content, str) else ""
                    break
                if round_number == MAX_TOOL_ROUNDS:
                    raise RuntimeError("Limite de rodadas de ferramentas do Hermes excedido.")

                identities: list[tuple[str, str]] = []
                for call in calls:
                    identity = _tool_call_identity(call)
                    if identity is None:
                        break
                    identities.append(identity)
                if len(identities) != len(calls):
                    _request_valid_tool_calls(messages, round_number)
                    continue

                messages.append(message)
                for call, identity in zip(calls, identities, strict=True):
                    tool_call_id, name = identity
                    tool_started = time.perf_counter()
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
                                result = {
                                    "error": {
                                        "code": raw_result["code"],
                                        "message": raw_result["message"],
                                    }
                                }
                                status = "error"
                            elif isinstance(raw_result, dict) and "error" in raw_result:
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
                            status = "error"
                            try:
                                error_payload = exc.response.json()
                                if isinstance(error_payload, dict):
                                    code = (
                                        error_payload.get("code")
                                        or f"http_{exc.response.status_code}"
                                    )
                                    message = (
                                        error_payload.get("message")
                                        or exc.response.text
                                        or "A chamada da ferramenta falhou."
                                    )
                                    result = {"error": {"code": code, "message": message}}
                                else:
                                    result = {
                                        "error": {
                                            "code": f"http_{exc.response.status_code}",
                                            "message": (
                                                exc.response.text
                                                or "A chamada da ferramenta falhou."
                                            ),
                                        }
                                    }
                            except Exception:
                                result = {
                                    "error": {
                                        "code": f"http_{exc.response.status_code}",
                                        "message": (
                                            exc.response.text or "A chamada da ferramenta falhou."
                                        ),
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
                {"system": SYSTEM_PROMPT, "task": task, "tools": TOOLS},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        task_id = _resolve_task_id(task, context, task_id)
        endpoint_id = f"endpoint-{hashlib.sha256(config.base_url.encode()).hexdigest()[:16]}"
        return ExperimentRun(
            **context.model_dump(exclude={"task_id"}),
            task_id=task_id,
            split=split,
            executor="hermes",
            repetition=repetition,
            code_commit=_git_commit(),
            harness_version=PROJECT_VERSION,
            adapter_version=PROJECT_VERSION,
            model=config.model,
            endpoint_id=endpoint_id,
            prompt_sha256=prompt_hash,
            parameters={
                "max_tool_rounds": MAX_TOOL_ROUNDS,
                "temperature": MODEL_TEMPERATURE,
                "seed": MODEL_SEED,
                "final_response": final_content,
            },
            started_at=started_at,
            latency_ms=(time.perf_counter() - started) * 1000,
            tool_calls=tool_calls,
            input_tokens=input_tokens if input_tokens_known else None,
            output_tokens=output_tokens if output_tokens_known else None,
            cost_usd=_calculate_cost_usd(
                config.model,
                config.base_url,
                input_tokens if input_tokens_known else None,
                output_tokens if output_tokens_known else None,
            ),
            agent_declared_success=bool(final_content.strip()),
            persisted_artifact_ids=persisted_artifact_ids,
            verified_success=None,
            evaluator=None,
        )


def _resolve_task_id(task: str, context: ToolContext, task_id: str | None) -> str:
    if task_id is not None:
        return task_id

    context_task_id = getattr(context, "task_id", None)
    if context_task_id is not None:
        return context_task_id

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


def _request_valid_tool_calls(messages: list[dict], round_number: int) -> None:
    if round_number == MAX_TOOL_ROUNDS:
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
    name = function.get("name")
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
