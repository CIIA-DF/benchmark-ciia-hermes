"""Physical request identity and transactional phases, independent of legacy stage rows."""

import logging
import time
from uuid import uuid4

from sqlalchemy import case, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import PhysicalToolAttempt
from services.backend.schema import physical_tool_attempts as attempts
from services.backend.schema import physical_tool_phases as phases

logger = logging.getLogger(__name__)


class ToolTracking:
    def __init__(self, engine):
        self.engine = engine

    def begin(self, tool, method):
        attempt_id = str(uuid4())
        now = time.time()
        with self.engine.begin() as conn:
            conn.execute(
                insert(attempts).values(
                    attempt_id=attempt_id,
                    tool=tool,
                    method=method,
                    started_at=now,
                    response_state="started",
                    client_received=None,
                )
            )
            conn.execute(
                insert(phases).values(attempt_id=attempt_id, phase="started", recorded_at=now)
            )
        return attempt_id

    def bind(self, conn, run_id, call, code=None):
        attempt_id = call.get("physical_attempt_id")
        if attempt_id is None:
            return
        values = dict(
            run_id=run_id, tool_call_id=call["tool_call_id"], args_sha256=call["args_sha256"]
        )
        if code is not None:
            values["code"] = code
        conn.execute(update(attempts).where(attempts.c.attempt_id == attempt_id).values(**values))

    def effect(self, conn, call, artifact_id, replayed):
        attempt_id = call.get("physical_attempt_id")
        if attempt_id is not None:
            conn.execute(
                insert(phases).values(
                    attempt_id=attempt_id,
                    phase="effect_confirmed",
                    recorded_at=time.time(),
                    artifact_id=artifact_id,
                    replayed=replayed,
                )
            )

    def complete(self, attempt_id, status, code=None):
        # This is a prepared HTTP response, never evidence that the client received it.
        phase = "interrupted" if status is None else "completed" if status < 400 else "failed"
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    update(attempts)
                    .where(attempts.c.attempt_id == attempt_id)
                    .values(
                        http_status=status,
                        code=code,
                        finished_at=time.time(),
                        response_state="interrupted" if status is None else "prepared",
                    )
                )
                conn.execute(
                    insert(phases).values(
                        attempt_id=attempt_id, phase=phase, recorded_at=time.time()
                    )
                )
        except SQLAlchemyError:
            # Preserve the effect/started phase and expose the collection gap without secrets.
            logger.warning("physical_attempt_completion_not_recorded attempt_id=%s", attempt_id)

    def history(self, conn, run_id):
        result = []
        for row in conn.execute(
            select(attempts)
            .where(attempts.c.run_id == str(run_id))
            .order_by(attempts.c.started_at, attempts.c.attempt_id)
        ).mappings():
            data = dict(row)
            data["phases"] = [
                dict(p)
                for p in conn.execute(
                    select(
                        phases.c.phase,
                        phases.c.recorded_at,
                        phases.c.artifact_id,
                        phases.c.replayed,
                    )
                    .where(phases.c.attempt_id == row["attempt_id"])
                    .order_by(
                        case(
                            (phases.c.phase == "started", 0),
                            (phases.c.phase == "effect_confirmed", 1),
                            else_=2,
                        ),
                        phases.c.phase,
                    )
                ).mappings()
            ]
            result.append(PhysicalToolAttempt.model_validate(data).model_dump(mode="json"))
        return result
