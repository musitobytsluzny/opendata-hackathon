"""Initial user/profile schema and baseline for existing development databases."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("firstname", sa.String(100), nullable=False),
        sa.Column("lastname", sa.String(100), nullable=False),
    )
    op.create_index("ix_profiles_id", "profiles", ["id"])


def downgrade():
    op.drop_table("profiles")
    op.drop_table("users")
