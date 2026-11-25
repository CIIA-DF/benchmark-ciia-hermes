from typing import NoReturn
from uuid import UUID

from contracts.models import ErrorCode, ToolError


class ToolFailure(Exception):
    def __init__(
        self,
        status: int,
        code: ErrorCode,
        message: str,
        run_id: UUID | str | None = None,
        *,
        retryable: bool = False,
    ):
        self.status = status
        self.error = ToolError(code=code, message=message, run_id=run_id, retryable=retryable)


def fail(
    status: int,
    code: ErrorCode,
    message: str,
    run_id: UUID | str | None = None,
    *,
    retryable: bool = False,
) -> NoReturn:
    raise ToolFailure(status, code, message, run_id, retryable=retryable)
