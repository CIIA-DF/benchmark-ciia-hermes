"""P9c: stream SSE parado não abre duas transações de escrita a cada 200 ms.

Antes, cada tick do laço chamava ``renew_stream`` (trava do principal e escrita) e
``read_events``, que rodava ``expire()`` (outra transação de escrita): cerca de 10 transações
por segundo por stream, disputando a trava do operador com ``POST /runs``.
"""

import asyncio
import contextlib

import httpx

from tests.backend.test_a9 import leases, start


def test_idle_stream_writes_rarely_and_still_stops_on_revocation(client, corpus, engine):
    run, _ = start(client, corpus)
    service = client.app.state.execution
    original = service.transaction
    opened = []

    @contextlib.contextmanager
    def counting():
        opened.append(1)
        with original() as conn:
            yield conn

    service.transaction = counting

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://test"
        ) as http:
            task = asyncio.create_task(
                http.get(f"/runs/{run['run_id']}/events", headers=client.operator_headers)
            )
            for _ in range(200):
                if leases(engine):
                    break
                await asyncio.sleep(0.01)
            assert len(leases(engine)) == 1
            before = len(opened)
            await asyncio.sleep(3)
            during = len(opened) - before
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return during

    try:
        during = asyncio.run(exercise())
    finally:
        service.transaction = original
    # ~15 ticks em 3 s: antes eram ~2 escritas por tick; agora só a manutenção a cada 2 s.
    assert during <= 4, during
    assert leases(engine) == []
