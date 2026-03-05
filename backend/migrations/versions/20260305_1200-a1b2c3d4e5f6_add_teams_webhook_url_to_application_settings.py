"""Add teams_webhook_url_encrypted to application_settings

Revision ID: a1b2c3d4e5f6
Revises: 7851d4d65ba5
Create Date: 2026-03-05 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "7851d4d65ba5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "application_settings",
        sa.Column("teams_webhook_url_encrypted", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("application_settings", "teams_webhook_url_encrypted")
