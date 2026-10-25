from alembic import op
from sqlalchemy import (
    JSON,
    Column,
    ForeignKeyConstraint,
    MetaData,
    String,
    Table,
)

revision = "0001"
down_revision = None
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


def upgrade():
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade():
    metadata.drop_all(op.get_bind(), checkfirst=False)
