"""Add the KRA Completion ranking criterion to properties that have criteria

Data only. Every property with ranking criteria but no "KRA Completion" row
gets one (weightage 10, max_points 100), and "Task Completion" goes from 25 to
15 only where it is still exactly 25, so customised weights are left alone.
Properties that then don't total 100 are not fixed here; they are for review.

Safe to re-run: the insert skips existing rows. The data is not reversed on
downgrade, because a weight of 15 may be someone's own choice.

Revision ID: 031_kra_completion_criterion
Revises: 030_kra_tasks
Create Date: 2026-10-30

"""
from alembic import op

revision = "031_kra_completion_criterion"
down_revision = "030_kra_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO ranking_criteria_config
            (id, tenant_id, property_id, criterion_name, weightage, max_points, description, is_active)
        SELECT gen_random_uuid(), existing.tenant_id, existing.property_id, 'KRA Completion', 10, 100,
               'Share of assigned KRA tasks completed, with half credit when completed after a delay', true
        FROM (SELECT DISTINCT tenant_id, property_id FROM ranking_criteria_config) AS existing
        WHERE NOT EXISTS (
            SELECT 1 FROM ranking_criteria_config c
            WHERE c.property_id = existing.property_id AND c.criterion_name = 'KRA Completion'
        )
        ON CONFLICT (property_id, criterion_name) DO NOTHING
    """)
    op.execute("""
        UPDATE ranking_criteria_config
        SET weightage = 15, updated_at = now()
        WHERE criterion_name = 'Task Completion' AND weightage = 25
    """)


def downgrade() -> None:
    pass
