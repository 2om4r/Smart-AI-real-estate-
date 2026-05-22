"""Add anomaly detection + sale tracking + PredictionLog

Revision ID: 5cafb6260849
Revises: 48bdf27d1c73
Create Date: 2026-05-22 02:49:31.564596

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5cafb6260849'
down_revision = '48bdf27d1c73'
branch_labels = None
depends_on = None


def upgrade():
    """Add 7 columns to property + create prediction_log table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── 1. Add new columns to property table ──────────────────────
    existing_cols = {c['name'] for c in inspector.get_columns('property')}
    new_cols = [
        ('flagged_anomaly',          sa.Boolean(),     {'server_default': sa.false()}),
        ('anomaly_severity',         sa.String(length=20),  {}),
        ('anomaly_reason',           sa.String(length=255), {}),
        ('ml_predicted_at_listing',  sa.Float(),       {}),
        ('sold_price',               sa.Float(),       {}),
        ('sold_date',                sa.DateTime(),    {}),
        ('days_on_market',           sa.Integer(),     {}),
    ]

    with op.batch_alter_table('property', schema=None) as batch_op:
        for col_name, col_type, col_kwargs in new_cols:
            if col_name not in existing_cols:
                batch_op.add_column(sa.Column(col_name, col_type, nullable=True, **col_kwargs))

    # ── 2. Create prediction_log table ───────────────────────────
    if 'prediction_log' not in inspector.get_table_names():
        op.create_table(
            'prediction_log',
            sa.Column('id',              sa.Integer(),    nullable=False),
            sa.Column('property_id',     sa.Integer(),    nullable=True),
            sa.Column('predicted_price', sa.Float(),      nullable=False),
            sa.Column('confidence',      sa.Float(),      nullable=True),
            sa.Column('model_version',   sa.String(length=40), nullable=True),
            sa.Column('actual_price',    sa.Float(),      nullable=True),
            sa.Column('error_pct',       sa.Float(),      nullable=True),
            sa.Column('listing_price',   sa.Float(),      nullable=True),
            sa.Column('features_json',   sa.Text(),       nullable=True),
            sa.Column('predicted_at',    sa.DateTime(),   nullable=False),
            sa.Column('confirmed_at',    sa.DateTime(),   nullable=True),
            sa.PrimaryKeyConstraint('id', name='pk_prediction_log'),
            sa.ForeignKeyConstraint(['property_id'], ['property.id'],
                                    name='fk_prediction_log_property_id_property',
                                    ondelete='SET NULL'),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'prediction_log' in inspector.get_table_names():
        op.drop_table('prediction_log')

    with op.batch_alter_table('property', schema=None) as batch_op:
        for col in ['days_on_market', 'sold_date', 'sold_price',
                    'ml_predicted_at_listing', 'anomaly_reason',
                    'anomaly_severity', 'flagged_anomaly']:
            batch_op.drop_column(col)
