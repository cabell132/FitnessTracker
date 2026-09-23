# ruff: noqa: INP001
"""Store VeSync scale measurements for the account owner."""

from alembic import op
import sqlalchemy as sa

revision = "d9b6e5a8f12c"
down_revision = "8d52a71c903e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the account owner's scale measurement table."""
    if sa.inspect(op.get_bind()).has_table("VeSyncWeighIn"):
        return
    op.create_table(
        "VeSyncWeighIn",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=False),
        sa.Column("impedance_ohms", sa.Float(), nullable=True),
        sa.Column("body_fat_pct", sa.Float(), nullable=True),
        sa.Column("is_manual_input", sa.Boolean(), nullable=False),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("weight_g > 0", name="ck_vesync_weigh_in_weight_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )
    op.create_index("ix_VeSyncWeighIn_measured_at", "VeSyncWeighIn", ["measured_at"])


def downgrade() -> None:
    """Remove the scale measurement table."""
    if not sa.inspect(op.get_bind()).has_table("VeSyncWeighIn"):
        return
    op.drop_index("ix_VeSyncWeighIn_measured_at", table_name="VeSyncWeighIn")
    op.drop_table("VeSyncWeighIn")
