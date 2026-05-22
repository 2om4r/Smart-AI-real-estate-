"""Add TrainingHistory table for ML retraining audit log

Revision ID: 48bdf27d1c73
Revises: 684a059b1a8f
Create Date: 2026-05-22 02:22:42.194751

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '48bdf27d1c73'
down_revision = '684a059b1a8f'
branch_labels = None
depends_on = None


def upgrade():
    """Create training_history table for ML audit log."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'training_history' not in inspector.get_table_names():
        op.create_table(
            'training_history',
            sa.Column('id',            sa.Integer(),     nullable=False),
            sa.Column('version',       sa.String(length=40),  nullable=False),
            sa.Column('model_path',    sa.String(length=255), nullable=False),
            sa.Column('r2_score',      sa.Float(),       nullable=True),
            sa.Column('rows_count',    sa.Integer(),     nullable=True),
            sa.Column('new_rows',      sa.Integer(),     nullable=True, server_default='0'),
            sa.Column('trained_at',    sa.DateTime(),    nullable=False),
            sa.Column('duration_sec',  sa.Float(),       nullable=True),
            sa.Column('trigger',       sa.String(length=30),  nullable=True),
            sa.Column('deployed',      sa.Boolean(),     nullable=True, server_default=sa.false()),
            sa.Column('is_active',     sa.Boolean(),     nullable=True, server_default=sa.false()),
            sa.Column('notes',         sa.Text(),        nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_training_history'),
            sa.UniqueConstraint('version', name='uq_training_history_version'),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'training_history' in inspector.get_table_names():
        op.drop_table('training_history')
