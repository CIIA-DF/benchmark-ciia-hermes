"""scripts.benchmark_batch: plano intercalado, idempotência, cota da fila e janela."""

import httpx
import pytest

from scripts.benchmark_batch import plan, submit


class Operator:
    """TestClient com os cabeçalhos do operador em cada chamada."""

    def __init__(self, client):
        self.client = client

    def get(self, path):
        return self.client.get(path, headers=self.client.operator_headers)

    def post(self, path, json):
        return self.client.post(path, json=json, headers=self.client.operator_headers)


def tasks(corpus, count=2):
    process, _ = corpus
    return [
        {
            "task_id": f"DEV-00{n}",
            "split": "development",
            "process_id": process.process_id,
            "corpus_version": process.corpus_version,
            "requirements_version": process.requirements_version,
            "prompt": f"Tarefa sintética {n}",
            "acceptance": ["gabarito que não pode chegar ao agente"],
        }
        for n in range(1, count + 1)
    ]


def finish_one(client):
    """Faz o papel do worker: reserva e encerra um run, liberando a fila."""
    claim = client.post(
        "/runs/claim", headers=client.worker_headers, json={"executor": "simulation"}
    )
    if claim.status_code == 204:
        return
    value = claim.json()
    headers = {**client.worker_headers, "X-Run-Token": value["run_token"]}
    response = client.post(
        f"/runs/{value['run_id']}/result",
        headers=headers,
        json={"status": "failed", "error_code": "adapter_error"},
    )
    assert response.status_code == 200, response.text


def test_plan_interleaves_executors_and_hides_acceptance(corpus):
    items = plan(tasks(corpus), ["hermes", "langgraph"], 2, "camada1-teste")
    # Intercalado e contrabalançado: a ordem dos executores gira por tarefa e por repetição.
    assert [(i["repetition"], i["task_id"], i["executor"]) for i in items] == [
        (1, "DEV-001", "hermes"),
        (1, "DEV-001", "langgraph"),
        (1, "DEV-002", "langgraph"),
        (1, "DEV-002", "hermes"),
        (2, "DEV-001", "langgraph"),
        (2, "DEV-001", "hermes"),
        (2, "DEV-002", "hermes"),
        (2, "DEV-002", "langgraph"),
    ]
    firsts = [items[n]["executor"] for n in range(0, len(items), 2)]
    assert firsts.count("hermes") == firsts.count("langgraph")
    assert len(items) == 8
    assert items[0]["idempotency_key"] == "camada1-teste:DEV-001:hermes:1"
    assert all("acceptance" not in i and i["task"].startswith("Tarefa") for i in items)


@pytest.mark.parametrize(
    "args",
    [
        (["hermes"], 1, "rótulo inválido"),
        ([], 1, "ok"),
        (["hermes"], 0, "ok"),
        # ":" separa as partes da chave; não pode aparecer dentro delas.
        (["hermes"], 1, "a:b"),
        (["her:mes"], 1, "ok"),
    ],
)
def test_plan_rejects_bad_input(corpus, args):
    with pytest.raises(ValueError):
        plan(tasks(corpus), *args)


def test_colon_in_task_id_cannot_collide_with_another_label(corpus):
    # Antes, --label a:b com a tarefa c e --label a com a tarefa b:c davam a mesma chave.
    colliding = [{**tasks(corpus, 1)[0], "task_id": "b:c"}]
    with pytest.raises(ValueError):
        plan(colliding, ["hermes"], 1, "a")
    key = plan(tasks(corpus, 1), ["hermes"], 1, "a-b")[0]["idempotency_key"]
    assert key == "a-b:DEV-001:hermes:1"


def test_rerun_with_same_label_reuses_runs(client, corpus):
    items = plan(tasks(corpus), ["simulation"], 2, "rodada-a")
    first = submit(Operator(client), items, window=10)
    again = submit(Operator(client), items, window=10)
    assert len(first) == 4 and [r["run_id"] for r in first] == [r["run_id"] for r in again]


def test_window_and_queue_quota_wait_for_workers(client, corpus):
    client.app.state.execution.max_queued_per_operator = 1
    items = plan(tasks(corpus, 3), ["simulation"], 1, "rodada-b")
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        finish_one(client)

    # Janela maior que a cota: o segundo POST recebe 429 resource_limit e espera o worker.
    manifest = submit(Operator(client), items, window=5, poll_seconds=0, sleep=sleep)
    assert [r["task_id"] for r in manifest] == ["DEV-001", "DEV-002", "DEV-003"]
    assert [r["position"] for r in manifest] == [1, 2, 3]
    assert len(sleeps) >= 2


# --- Terceira revisão (21/11): falhas passageiras, prazo sem progresso e manifesto completo ---


class Flaky(Operator):
    """Injeta falhas antes de delegar ao backend real; conta as chamadas por método."""

    def __init__(self, client, post=(), get=()):
        super().__init__(client)
        self.failures = {"post": list(post), "get": list(get)}
        self.calls = {"post": 0, "get": 0}

    def _maybe_fail(self, method, path):
        self.calls[method] += 1
        if self.failures[method]:
            failure = self.failures[method].pop(0)
            if isinstance(failure, Exception):
                raise failure
            if failure is not None:
                return httpx.Response(
                    failure[0],
                    json=failure[1],
                    request=httpx.Request(method.upper(), "http://testserver" + path),
                )
        return None

    def get(self, path):
        return self._maybe_fail("get", path) or super().get(path)

    def post(self, path, json):
        return self._maybe_fail("post", path) or super().post(path, json)


UNAVAILABLE = (503, {"code": "storage_unavailable", "message": "x", "retryable": True})
FORBIDDEN = (403, {"code": "forbidden", "message": "x", "retryable": False})


class Clock:
    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        return self.now

    def advance(self):
        self.now += self.step


def test_transient_503_on_post_is_retried_without_duplicate_run(client, corpus):
    items = plan(tasks(corpus), ["simulation"], 1, "rodada-c")
    http = Flaky(client, post=[UNAVAILABLE, UNAVAILABLE])
    sleeps = []
    manifest = submit(http, items, window=10, sleep=sleeps.append)
    assert [r["status"] for r in manifest] == ["queued", "queued"]
    assert sleeps[:2] == [1.0, 2.0] and http.calls["post"] == 4
    # Mesmo rótulo de novo: as mesmas chaves devolvem os mesmos runs (nenhum duplicado).
    again = submit(Operator(client), items, window=10)
    assert [r["run_id"] for r in again] == [r["run_id"] for r in manifest]


def test_transport_error_while_polling_does_not_stop_the_batch(client, corpus):
    items = plan(tasks(corpus), ["simulation"], 1, "rodada-d")
    http = Flaky(client, get=[httpx.ConnectError("backend reiniciando")])

    def sleep(seconds):
        finish_one(client)

    manifest = submit(http, items, window=1, poll_seconds=0, sleep=sleep)
    assert len(manifest) == 2 and http.calls["get"] >= 2


def test_definitive_error_is_not_retried_and_lists_unsent_items(client, corpus):
    items = plan(tasks(corpus, 3), ["simulation"], 1, "rodada-e")
    http = Flaky(client, post=[None, FORBIDDEN])
    rows = []
    with pytest.raises(httpx.HTTPStatusError):
        submit(
            http,
            items,
            window=10,
            sleep=lambda s: pytest.fail("403 não é repetido"),
            emit=rows.append,
        )
    assert http.calls["post"] == 2
    assert [(r["position"], r["status"]) for r in rows] == [
        (1, "queued"),
        (2, "not_submitted"),
        (3, "not_submitted"),
    ]
    assert rows[1]["run_id"] is None and rows[2]["task_id"] == "DEV-003"


def test_batch_with_progress_outlives_the_stall_window(client, corpus):
    items = plan(tasks(corpus, 3), ["simulation"], 1, "rodada-f")
    clock = Clock(step=1000)

    def sleep(seconds):
        clock.advance()
        finish_one(client)

    # 3 runs com janela 1: ~3000 s simulados, mais que stall_seconds, mas sempre com progresso.
    manifest = submit(
        Operator(client),
        items,
        window=1,
        poll_seconds=0,
        stall_seconds=1200,
        sleep=sleep,
        clock=clock,
    )
    assert len(manifest) == 3 and clock.now >= 2000


def test_batch_without_progress_stops_and_reports_unsent(client, corpus):
    items = plan(tasks(corpus), ["simulation"], 1, "rodada-g")
    clock = Clock(step=500)
    rows = []
    with pytest.raises(TimeoutError):
        submit(
            Operator(client),
            items,
            window=1,
            poll_seconds=0,
            stall_seconds=1200,
            sleep=lambda s: clock.advance(),
            clock=clock,
            emit=rows.append,
        )
    assert [(r["position"], r["status"]) for r in rows] == [(1, "queued"), (2, "not_submitted")]
