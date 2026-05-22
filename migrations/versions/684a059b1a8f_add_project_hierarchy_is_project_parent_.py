"""Add Project hierarchy: is_project, parent_project_id, developer, completion_date

Revision ID: 684a059b1a8f
Revises: aab1a83349c8
Create Date: 2026-05-21 17:05:43.014705

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '684a059b1a8f'
down_revision = 'aab1a83349c8'
branch_labels = None
depends_on = None


def upgrade():
    """Add 4 new columns to property table for project hierarchy."""
    with op.batch_alter_table('property', schema=None) as batch_op:
        # is_project: existing rows get FALSE via server_default
        batch_op.add_column(sa.Column(
            'is_project', sa.Boolean(),
            nullable=False, server_default=sa.false()
        ))
        batch_op.add_column(sa.Column(
            'parent_project_id', sa.Integer(), nullable=True
        ))
        batch_op.add_column(sa.Column(
            'developer', sa.String(length=100), nullable=True
        ))
        batch_op.add_column(sa.Column(
            'completion_date', sa.String(length=50), nullable=True
        ))
        # FK constraint must have an explicit name for SQLite batch mode
        batch_op.create_foreign_key(
            'fk_property_parent_project_id_property',
            'property', ['parent_project_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_property_parent_project_id_property', type_='foreignkey'
        )
        batch_op.drop_column('completion_date')
        batch_op.drop_column('developer')
        batch_op.drop_column('parent_project_id')
        batch_op.drop_column('is_project')
