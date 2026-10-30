"""Release durable SSE admission even if response iteration never starts."""

import logging
from collections.abc import Callable

from anyio import CancelScope
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)


class LeasedStreamingResponse(StreamingResponse):
    def __init__(self, content, *, release: Callable[[], None], **kwargs):
        super().__init__(content, **kwargs)
        self.release = release

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Starlette cancels the response task on disconnect; cleanup still owns its lease.
            with CancelScope(shield=True):
                try:
                    await run_in_threadpool(self.release)
                except SQLAlchemyError:
                    # Database failure cannot promise immediate release; durable TTL recovers it.
                    logger.warning("stream_lease_release_unavailable")
