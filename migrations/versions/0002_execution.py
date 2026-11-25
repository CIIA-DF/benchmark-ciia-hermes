from alembic import op
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

metadata = MetaData()
processes = Table(
    "processes",
    metadata,
    Column("process_id", String, primary_key=True),
    Column("corpus_version", String, primary_key=True),
    Column("payload", JSON, nullable=False),
)
documents = Table(
    "documents",
    metadata,
    Column("process_id", String, primary_key=True),
    Column("corpus_version", String, primary_key=True),
    Column("document_id", String, primary_key=True),
    Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(
        ["process_id", "corpus_version"], ["processes.process_id", "processes.corpus_version"]
    ),
)
chunks = Table(
    "chunks",
    metadata,
    Column("chunk_id", String, primary_key=True),
    Column("process_id", String, nullable=False, index=True),
    Column("corpus_version", String, nullable=False),
    Column("document_id", String, nullable=False),
    Column("text", String, nullable=False),
    Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(
        ["process_id", "corpus_version", "document_id"],
        ["documents.process_id", "documents.corpus_version", "documents.document_id"],
    ),
)


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


def upgrade():
    metadata.create_all(
        op.get_bind(),
        tables=[
            t for t in metadata.sorted_tables if t.name not in {"processes", "documents", "chunks"}
        ],
        checkfirst=False,
    )


def downgrade():
    for table in reversed(metadata.sorted_tables):
        if table.name not in {"processes", "documents", "chunks"}:
            table.drop(op.get_bind(), checkfirst=False)
