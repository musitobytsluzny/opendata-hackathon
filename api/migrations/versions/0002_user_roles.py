"""Assign the least privileged role to every existing account."""

import sqlalchemy as sa
from alembic import op

revision = "0002_user_roles"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("role", sa.String(5), nullable=False, server_default="user"))
    op.create_check_constraint("user_role", "users", "role IN ('user', 'admin')")


def downgrade():
    op.drop_constraint("user_role", "users", type_="check")
    op.drop_column("users", "role")
