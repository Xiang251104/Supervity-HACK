"""Add the self-learning policies.

Learning from human corrections is governed the same way every other behaviour is
governed here: by rows in ap_policies that a business user edits in the UI. It is
not a hidden model and it has no separate control panel — a judge switches it on,
off, or up in exactly the same place as the price tolerance.

Seeded as 'advise' on purpose. On a fresh clone the system reports what it could
have learned without silently changing a money decision; turning it up to 'apply'
is a deliberate, logged, no-code act.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO ap_policies (key, name, description, value_type, value, options, unit,
                                 severity, active, version, updated_by) VALUES
        ('LEARNED-OVERRIDES',
         'Learn from reviewer decisions',
         'What to do when a reviewer has already approved the same reason for the same '
         'vendor several times. off ignores the history. advise shows it without changing '
         'the verdict. apply softens the verdict by one step. Only data-quality reasons can '
         'ever be learned — bank, duplicate, blocked-vendor and approval controls never are.',
         'enum', '"advise"'::json, '["off","advise","apply"]'::json, NULL,
         'advise', true, 1, 'system'),

        ('LEARN-CONFIRMATIONS',
         'Approvals before learning',
         'How many times a reviewer must approve the same reason for the same vendor before '
         'the system treats it as settled. Higher is more cautious.',
         'number', '3'::json, NULL, 'approvals', 'advise', true, 1, 'system')
        """
    )
    op.execute(
        """
        INSERT INTO ap_policy_versions (policy_key, version, value, changed_by, note)
        SELECT key, 1, value, 'system', 'Initial seed'
        FROM ap_policies
        WHERE key IN ('LEARNED-OVERRIDES', 'LEARN-CONFIRMATIONS')
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ap_policy_versions "
        "WHERE policy_key IN ('LEARNED-OVERRIDES', 'LEARN-CONFIRMATIONS')"
    )
    op.execute(
        "DELETE FROM ap_policies "
        "WHERE key IN ('LEARNED-OVERRIDES', 'LEARN-CONFIRMATIONS')"
    )
