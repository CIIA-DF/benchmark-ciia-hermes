"""Adaptador Hermes com loop ReAct sobre a API OpenAI-compatible."""

import hashlib
import json
import os
import time
from datetime import UTC, datetime

import httpx

from agents.hermes.tools import TOOLS
from agents.interface import AgentAdapter, ModelConfig, ToolClient
from contracts.models import ExperimentRun, ToolCallRecord, ToolContext

SYSTEM_PROMPT = (
    "Responda à tarefa usando as ferramentas disponíveis quando necessário. "
    "Baseie a resposta somente nas evidências retornadas e explicite limitações."
)
MAX_TOOL_ROUNDS = 10
PROJECT_VERSION = "0.1.0"


class HermesAdapter(AgentAdapter):
    def run(self, task: str, context: ToolContext) -> ExperimentRun:
        config = ModelConfig.from_environment()
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        tool_client = ToolClient("http://127.0.0.1:8000")
        tool_calls: list[ToolCallRecord] = []
        input_tokens = 0
        output_tokens = 0
        input_tokens_known = True
        output_tokens_known = True
        final_content = ""

        with httpx.Client(timeout=config.timeout_seconds) as client:
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

                calls = message.get("tool_calls") or []
                if not isinstance(calls, list):
                    raise ValueError("Resposta da LLM contém tool_calls inválido.")
                if not calls:
                    content = message.get("content")
                    final_content = content if isinstance(content, str) else ""
                    break
                if round_number == MAX_TOOL_ROUNDS:
                    raise RuntimeError("Limite de rodadas de ferramentas do Hermes excedido.")

                messages.append(message)
                for call in calls:
                    tool_call_id, name, arguments = _parse_tool_call(call)
                    tool_started = time.perf_counter()
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


def _first_choice(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Resposta da LLM deve ser um objeto JSON.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Resposta da LLM sem choices válidas.")
    return choices[0]


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
