"""Banking domain: students -> employees, dataset visibility, document metadata, app audience

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- students -> employees ---
    op.rename_table("students", "employees")
    op.alter_column("employees", "student_id", new_column_name="employee_code")
    op.execute("ALTER INDEX IF EXISTS ix_students_email RENAME TO ix_employees_email")
    op.execute("ALTER INDEX IF EXISTS ix_students_student_id RENAME TO ix_employees_employee_code")
    op.execute("ALTER TABLE employees RENAME CONSTRAINT students_pkey TO employees_pkey")
    op.execute("ALTER TABLE employees RENAME CONSTRAINT students_email_key TO employees_email_key")
    op.add_column("employees", sa.Column("branch", sa.String(255), nullable=True))
    op.add_column("employees", sa.Column("department", sa.String(255), nullable=True))
    op.add_column("employees", sa.Column("position", sa.String(64), nullable=True))

    # --- conversations.student_id -> employee_id ---
    op.alter_column("conversations", "student_id", new_column_name="employee_id")
    op.execute("ALTER INDEX IF EXISTS ix_conversations_student_app RENAME TO ix_conversations_employee_app")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'conversations_student_id_fkey'
            ) THEN
                ALTER TABLE conversations
                    RENAME CONSTRAINT conversations_student_id_fkey TO conversations_employee_id_fkey;
            END IF;
        END $$;
        """
    )

    # --- ai_providers.purpose was never migrated (model has it; legacy DBs added it by hand) ---
    op.execute(
        "ALTER TABLE ai_providers ADD COLUMN IF NOT EXISTS purpose VARCHAR(32) NOT NULL DEFAULT 'embedding'"
    )

    # --- datasets: visibility (internal | public) ---
    op.add_column(
        "datasets",
        sa.Column("visibility", sa.String(16), nullable=False, server_default="internal"),
    )

    # --- documents: banking metadata shown in citations ---
    op.add_column("documents", sa.Column("doc_type", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("version", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("effective_from", sa.String(32), nullable=True))

    # --- apps: audience (staff | customer) ---
    op.add_column(
        "apps",
        sa.Column("audience", sa.String(16), nullable=False, server_default="staff"),
    )


def downgrade() -> None:
    op.drop_column("apps", "audience")
    op.drop_column("documents", "effective_from")
    op.drop_column("documents", "version")
    op.drop_column("documents", "doc_type")
    op.drop_column("datasets", "visibility")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'conversations_employee_id_fkey'
            ) THEN
                ALTER TABLE conversations
                    RENAME CONSTRAINT conversations_employee_id_fkey TO conversations_student_id_fkey;
            END IF;
        END $$;
        """
    )
    op.execute("ALTER INDEX IF EXISTS ix_conversations_employee_app RENAME TO ix_conversations_student_app")
    op.alter_column("conversations", "employee_id", new_column_name="student_id")

    op.drop_column("employees", "position")
    op.drop_column("employees", "department")
    op.drop_column("employees", "branch")
    op.execute("ALTER TABLE employees RENAME CONSTRAINT employees_email_key TO students_email_key")
    op.execute("ALTER TABLE employees RENAME CONSTRAINT employees_pkey TO students_pkey")
    op.execute("ALTER INDEX IF EXISTS ix_employees_employee_code RENAME TO ix_students_student_id")
    op.execute("ALTER INDEX IF EXISTS ix_employees_email RENAME TO ix_students_email")
    op.alter_column("employees", "employee_code", new_column_name="student_id")
    op.rename_table("employees", "students")
