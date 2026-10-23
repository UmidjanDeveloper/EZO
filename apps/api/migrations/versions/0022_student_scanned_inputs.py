"""Student raw inputs may be scanned images (PNG/JPEG) for isolated OCR.

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("student_raw_revisions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_student_raw_revisions_format", type_="check")
        batch_op.create_check_constraint(
            "ck_student_raw_revisions_format", "format IN ('pdf','docx','epub','png','jpeg')"
        )


def downgrade() -> None:
    # Fails (rather than silently deleting sources) if image inputs exist.
    with op.batch_alter_table("student_raw_revisions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_student_raw_revisions_format", type_="check")
        batch_op.create_check_constraint(
            "ck_student_raw_revisions_format", "format IN ('pdf','docx','epub')"
        )
