"""make commit identity repository-local

Revision ID: i1c2d3e4f5a6
Revises: h2c3d4e5f6a7
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "i1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "h2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Earlier releases used a global hash primary key. Existing rows already
    # name their repository; align owner_id with it before changing identity.
    op.execute(
        "UPDATE commits SET owner_id = repos.owner_id "
        "FROM repos WHERE commits.repo_id = repos.id "
        "AND commits.owner_id IS DISTINCT FROM repos.owner_id"
        if bind.dialect.name == "postgresql"
        else "UPDATE commits SET owner_id = (SELECT owner_id FROM repos WHERE repos.id = commits.repo_id)"
    )
    with op.batch_alter_table("commits") as batch:
        batch.drop_constraint("commits_pkey", type_="primary")
        batch.create_primary_key("commits_pkey", ["repo_id", "hash"])
    op.create_index("ix_commits_owner_repo_date", "commits", ["owner_id", "repo_id", "date"])


def downgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text("SELECT 1 FROM commits GROUP BY hash HAVING count(*) > 1 LIMIT 1")
    ).first()
    if duplicate:
        raise RuntimeError("Cannot downgrade: repository-local commit hashes would be lost")
    op.drop_index("ix_commits_owner_repo_date", table_name="commits")
    with op.batch_alter_table("commits") as batch:
        batch.drop_constraint("commits_pkey", type_="primary")
        batch.create_primary_key("commits_pkey", ["hash"])
