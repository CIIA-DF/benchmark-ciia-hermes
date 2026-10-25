from contracts.models import ToolError


class ToolFailure(Exception):
    def __init__(self, status: int, code: str, message: str, run_id=None):
        self.status = status
        self.error = ToolError(code=code, message=message, run_id=run_id)


def fail(status, code, message, run_id=None):
    raise ToolFailure(status, code, message, run_id)
