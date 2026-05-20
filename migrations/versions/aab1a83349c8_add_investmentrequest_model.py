"""add InvestmentRequest model

Revision ID: aab1a83349c8
Revises:
Create Date: 2026-05-20 15:49:52.702885

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aab1a83349c8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create investment_request table only if it doesn't already exist.
    # db.create_all() may have already created it; op.create_table is idempotent
    # because we check with get_bind() first.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'investment_request' not in inspector.get_table_names():
        op.create_table(
            'investment_request',
            sa.Column('id',        sa.Integer(),     nullable=False),
            sa.Column('user_id',   sa.Integer(),     nullable=True),
            sa.Column('agent_id',  sa.Integer(),     nullable=False),
            sa.Column('project',   sa.String(50),    nullable=True),
            sa.Column('message',   sa.Text(),        nullable=True),
            sa.Column('status',    sa.String(20),    nullable=False, server_default='pending'),
            sa.Column('timestamp', sa.DateTime(),    nullable=False),
            sa.ForeignKeyConstraint(['agent_id'], ['user.id'],
                                    name='fk_investment_request_agent_id_user'),
            sa.ForeignKeyConstraint(['user_id'],  ['user.id'],
                                    name='fk_investment_request_user_id_user'),
            sa.PrimaryKeyConstraint('id', name='pk_investment_request'),
        )


def downgrade():
    op.drop_table('investment_request')
