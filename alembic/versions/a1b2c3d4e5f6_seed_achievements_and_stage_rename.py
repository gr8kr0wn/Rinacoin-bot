"""seed achievements and rename egg to kitten

Revision ID: a1b2c3d4e5f6
Revises: 0f023d210eda
Create Date: 2026-07-03 12:00:00.000000

"""
from typing import Sequence, Union
from uuid import uuid5, NAMESPACE_DNS

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import table, column

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0f023d210eda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACHIEVEMENTS = [
    {
        "code": "first_daily",
        "name": "First Treat",
        "description": "Claim your first daily reward",
        "points_reward": 5,
        "icon": "🌟",
    },
    {
        "code": "streak_7",
        "name": "Week Warrior",
        "description": "Maintain a 7-day daily streak",
        "points_reward": 20,
        "icon": "🔥",
    },
    {
        "code": "streak_30",
        "name": "Monthly Devotion",
        "description": "Maintain a 30-day daily streak",
        "points_reward": 100,
        "icon": "💎",
    },
    {
        "code": "referral_1",
        "name": "Cat Ambassador",
        "description": "Refer your first friend",
        "points_reward": 10,
        "icon": "🎁",
    },
    {
        "code": "referral_5",
        "name": "Social Butterfly",
        "description": "Refer 5 friends",
        "points_reward": 50,
        "icon": "🦋",
    },
    {
        "code": "points_100",
        "name": "Hundred Club",
        "description": "Earn 100 lifetime points",
        "points_reward": 10,
        "icon": "💯",
    },
    {
        "code": "points_1000",
        "name": "Points Millionaire",
        "description": "Earn 1,000 lifetime points",
        "points_reward": 50,
        "icon": "💰",
    },
    {
        "code": "level_5",
        "name": "Growing Up",
        "description": "Reach level 5",
        "points_reward": 25,
        "icon": "📈",
    },
    {
        "code": "level_10",
        "name": "Cat Whisperer",
        "description": "Reach level 10",
        "points_reward": 100,
        "icon": "👑",
    },
    {
        "code": "messages_50",
        "name": "Chatty Cat",
        "description": "Send 50 message-activity messages",
        "points_reward": 15,
        "icon": "💬",
    },
]


def upgrade() -> None:
    achievements_table = table(
        "achievements",
        column("code", sa.Text),
        column("name", sa.Text),
        column("description", sa.Text),
        column("points_reward", sa.Integer),
        column("icon", sa.Text),
    )
    op.bulk_insert(achievements_table, ACHIEVEMENTS)

    op.alter_column("pet_state", "stage",
        server_default="kitten",
        existing_server_default="egg",
        existing_type=sa.Text,
    )


def downgrade() -> None:
    op.execute("DELETE FROM achievements WHERE code IN ({})".format(
        ",".join(f"'{a['code']}'" for a in ACHIEVEMENTS)
    ))
    op.alter_column("pet_state", "stage",
        server_default="egg",
        existing_server_default="kitten",
        existing_type=sa.Text,
    )
