"""initial_schema

Revision ID: 0f023d210eda
Revises: 
Create Date: 2026-07-02 06:53:29.941644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0f023d210eda'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('achievements',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('points_reward', sa.Integer(), server_default='0', nullable=False),
        sa.Column('icon', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )

    op.create_table('users',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('wallet_address', sa.Text(), nullable=True),
        sa.Column('level', sa.Integer(), server_default='1', nullable=False),
        sa.Column('points', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('lifetime_points', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('daily_streak', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_daily_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_banned', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('referred_by', sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id'),
        sa.UniqueConstraint('wallet_address'),
    )
    op.create_index('points_idx', 'users', [sa.text('points DESC')])
    op.create_index('referred_by_idx', 'users', ['referred_by'])

    op.create_table('activity_log',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('points_delta', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('user_id_created_at_idx', 'activity_log', ['user_id', sa.text('created_at DESC')])

    op.create_table('pet_state',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('community_id', sa.BigInteger(), nullable=False),
        sa.Column('mood', sa.Text(), server_default='happy', nullable=False),
        sa.Column('mood_score', sa.Integer(), server_default='0', nullable=False),
        sa.Column('energy', sa.Integer(), server_default='50', nullable=False),
        sa.Column('last_interacted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_mood_change_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stage', sa.Text(), server_default='egg', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('community_id'),
    )

    op.create_table('referrals',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('referrer_id', sa.Uuid(), nullable=False),
        sa.Column('referred_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.Text(), server_default='pending', nullable=False),
        sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('referred_id'),
        sa.ForeignKeyConstraint(['referrer_id'], ['users.id']),
        sa.ForeignKeyConstraint(['referred_id'], ['users.id']),
    )

    op.create_table('user_achievements',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('achievement_id', sa.Uuid(), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'achievement_id', name='user_achievement_uniq'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievements.id']),
    )

    op.create_table('ai_message_log',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('prompt_type', sa.Text(), nullable=False),
        sa.Column('input_context', postgresql.JSONB(), nullable=True),
        sa.Column('output_text', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )

    op.create_table('admin_actions',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('admin_user_id', sa.Uuid(), nullable=False),
        sa.Column('action_type', sa.Text(), nullable=False),
        sa.Column('target_user_id', sa.Uuid(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id']),
    )

    op.create_table('job_runs',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('job_name', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('job_runs')
    op.drop_table('admin_actions')
    op.drop_table('ai_message_log')
    op.drop_table('user_achievements')
    op.drop_table('referrals')
    op.drop_table('pet_state')
    op.drop_table('activity_log')
    op.drop_table('users')
    op.drop_table('achievements')
