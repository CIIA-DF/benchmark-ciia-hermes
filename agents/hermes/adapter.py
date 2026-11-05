"""Adaptador Hermes com loop ReAct sobre a API OpenAI-compatible."""

import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime

import httpx

from agents.hermes.tools import TOOLS
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
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class HermesAdapter(AgentAdapter):
    def __init__(self):
        self.final_response = ""

    def run(self, task: str, context: ToolContext) -> ExperimentRun:
        self.final_response = ""
        config = _model_config_from_environment()
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        tool_client = ToolClient(os.getenv("BACKEND_URL", "http://127.0.0.1:8000"))
        tool_calls: list[ToolCallRecord] = []
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
                    headers={"Authorization": f"Bearer {config.api_key}"},
                    json={
                        "model": config.model,
                        "messages": messages,
                        "tools": TOOLS,
                        "tool_choice": "auto",
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
                            "error": (
                                "Argumentos inválidos: envie um objeto JSON válido "
                                "para a ferramenta."
                            )
                        }
                        status = "error"
                    else:
                        try:
                            result = tool_client.call(name, arguments)
                            status = "ok"
                        except (httpx.HTTPError, ValueError):
                            result = {"error": "A chamada da ferramenta falhou."}
                            status = "error"
                    duration_ms = (time.perf_counter() - tool_started) * 1000
                    tool_calls.append(
                        ToolCallRecord(
                            tool_call_id=tool_call_id,
                            tool=name,
                            duration_ms=duration_ms,
                            status=status,
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
        task_id = f"task-{hashlib.sha256(task.encode('utf-8')).hexdigest()[:16]}"
        endpoint_id = f"endpoint-{hashlib.sha256(config.base_url.encode()).hexdigest()[:16]}"
        return ExperimentRun(
            **context.model_dump(),
            task_id=task_id,
            split="development",
            executor="hermes",
            repetition=1,
            code_commit=os.getenv("GIT_COMMIT", "unknown"),
            harness_version=PROJECT_VERSION,
            adapter_version=PROJECT_VERSION,
            model=config.model,
            endpoint_id=endpoint_id,
            prompt_sha256=prompt_hash,
            parameters={"max_tool_rounds": MAX_TOOL_ROUNDS},
            started_at=started_at,
            latency_ms=(time.perf_counter() - started) * 1000,
            tool_calls=tool_calls,
            input_tokens=input_tokens if input_tokens_known else None,
            output_tokens=output_tokens if output_tokens_known else None,
            agent_declared_success=bool(final_content.strip()),
            persisted_artifact_ids=[],
            verified_success=None,
            evaluator=None,
        )


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
