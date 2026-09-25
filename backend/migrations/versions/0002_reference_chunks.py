"""Local reference embeddings; case tables are unchanged.

Revision ID: 0002_reference_chunks
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002_reference_chunks"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.create_table(
        "reference_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("model_key", sa.String(), nullable=False),
        sa.Column("embedding", Vector(384).with_variant(sa.JSON(), "sqlite"), nullable=False),
    )
    op.create_index("ix_reference_chunks_source", "reference_chunks", ["source"])


def downgrade() -> None:
    op.drop_table("reference_chunks")
    # The database-wide extension may be used by other schemas; never drop it here.
