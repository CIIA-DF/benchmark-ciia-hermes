"""Tabelas do fluxo de execução; alterações exigem uma nova revisão Alembic."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)

from services.backend.storage import metadata

principals = Table(
    "principals",
    metadata,
    Column("principal_id", String, primary_key=True),
    Column("token_sha256", String, nullable=False, unique=True),
    Column("role", String, nullable=False),
    Column("executor", String),
    Column("can_write", Boolean, nullable=False),
)
permissions = Table(
    "process_permissions",
    metadata,
    Column("principal_id", String, ForeignKey("principals.principal_id"), primary_key=True),
    Column("process_id", String, primary_key=True),
    Column("corpus_version", String, primary_key=True),
)
requirements = Table(
    "requirements",
    metadata,
    Column("process_id", String, primary_key=True),
    Column("corpus_version", String, primary_key=True),
    Column("requirements_version", String, primary_key=True),
    Column("requirement_id", String, primary_key=True),
    Column("payload", JSON, nullable=False),
)
conversations = Table(
    "conversations",
    metadata,
    Column("conversation_id", String, primary_key=True),
    Column("owner_id", String, ForeignKey("principals.principal_id"), nullable=False),
    Column("participant_id", String(36), nullable=True, index=True),
    Column("process_id", String, nullable=False),
    Column("corpus_version", String, nullable=False),
    Column("requirements_version", String, nullable=False),
    Column("executor", String, nullable=False),
    Column("created_at", Float, nullable=False),
)
runs = Table(
    "runs",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("owner_id", String, ForeignKey("principals.principal_id"), nullable=False),
    Column("conversation_id", String, ForeignKey("conversations.conversation_id")),
    Column("idempotency_key", String, nullable=False),
    Column("input_sha256", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("executor", String, nullable=False),
    Column("status", String, nullable=False, index=True),
    Column("context", JSON, nullable=False),
    Column("history", JSON, nullable=False),
    Column("task", String, nullable=False),
    Column("task_metadata", JSON, nullable=False),
    Column("worker_id", String, ForeignKey("principals.principal_id")),
    Column("lease_sha256", String),
    Column("lease_until", Float),
    Column("created_at", Float, nullable=False),
    Column("started_at", Float),
    Column("finished_at", Float),
    Column("event_sequence", Integer, nullable=False),
    Column("result", JSON),
    Column("result_sha256", String),
    UniqueConstraint("owner_id", "idempotency_key", name="uq_runs_owner_key"),
)
messages = Table(
    "messages",
    metadata,
    Column("message_id", String, primary_key=True),
    Column("conversation_id", String, ForeignKey("conversations.conversation_id"), nullable=False),
    Column("run_id", String, ForeignKey("runs.run_id"), nullable=False),
    Column("role", String, nullable=False),
    Column("content", String, nullable=False),
    Column("created_at", Float, nullable=False),
    UniqueConstraint("run_id", "role", name="uq_messages_run_role"),
)
events = Table(
    "run_events",
    metadata,
    Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("event_id", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", Float, nullable=False),
    UniqueConstraint("run_id", "event_id", name="uq_events_run_event"),
)
artifacts = Table(
    "artifacts",
    metadata,
    Column("artifact_id", String, primary_key=True),
    Column("run_id", String, ForeignKey("runs.run_id"), nullable=False),
    Column("tool", String, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("input_sha256", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("receipt", JSON, nullable=False),
    UniqueConstraint("run_id", "tool", "idempotency_key", name="uq_artifact_operation"),
)
# Cada tentativa de tool, inclusive falhas e replays; argumentos só como hash.
tool_calls = Table(
    "tool_calls",
    metadata,
    Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
    Column("tool_call_id", String, primary_key=True),
    Column("attempt", Integer, primary_key=True),
    Column("tool", String, nullable=False),
    Column("started_at", Float, nullable=False),
    Column("duration_ms", Float, nullable=False),
    Column("http_status", Integer, nullable=False),
    Column("code", String),
    Column("replayed", Boolean, nullable=False),
    Column("artifact_id", String),
    Column("args_sha256", String, nullable=False),
)


logical_tool_calls = Table(
    "logical_tool_calls",
    metadata,
    Column("run_id", String, ForeignKey("runs.run_id"), primary_key=True),
    Column("tool_call_id", String, primary_key=True),
    Column("tool", String, nullable=False),
    Column("args_sha256", String, nullable=False),
)


# Canonical physical HTTP attempts. Pre-0006 tool_calls remain a compatibility ledger.
physical_tool_attempts = Table(
    "physical_tool_attempts",
    metadata,
    Column("attempt_id", String(36), primary_key=True),
    Column("tool", String, nullable=False),
    Column("method", String, nullable=False),
    Column("run_id", String, ForeignKey("runs.run_id"), nullable=True, index=True),
    Column("tool_call_id", String, nullable=True),
    Column("args_sha256", String, nullable=True),
    Column("started_at", Float, nullable=False),
    Column("finished_at", Float, nullable=True),
    Column("response_state", String, nullable=False),
    Column("http_status", Integer, nullable=True),
    Column("code", String, nullable=True),
    Column("client_received", Boolean, nullable=True),
)
physical_tool_phases = Table(
    "physical_tool_phases",
    metadata,
    Column(
        "attempt_id", String(36), ForeignKey("physical_tool_attempts.attempt_id"), primary_key=True
    ),
    Column("phase", String, primary_key=True),
    Column("recorded_at", Float, nullable=False),
    Column("artifact_id", String, ForeignKey("artifacts.artifact_id"), nullable=True),
    Column("replayed", Boolean, nullable=True),
)

# Successful worker polling/heartbeats, not proof of inference connectivity.
worker_presence = Table(
    "worker_presence",
    metadata,
    Column("principal_id", String, ForeignKey("principals.principal_id"), primary_key=True),
    Column("executor", String, nullable=False),
    Column("observed_at", Float, nullable=False),
    Column("source", String, nullable=False),
)

# Active SSE admission; abandoned responses expire without an in-memory owner.
stream_leases = Table(
    "stream_leases",
    metadata,
    Column("lease_id", String(36), primary_key=True),
    Column(
        "principal_id", String, ForeignKey("principals.principal_id"), nullable=False, index=True
    ),
    Column("run_id", String, ForeignKey("runs.run_id"), nullable=False),
    Column("lease_until", Float, nullable=False),
)
