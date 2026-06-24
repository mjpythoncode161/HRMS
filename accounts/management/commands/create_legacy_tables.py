"""
Create SQLite tables for legacy HRMS models (managed=False).

These tables are normally populated by `import_mysql_dump`, but an empty
schema is enough for a fresh local install to run without errors.
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create database tables for unmanaged legacy HRMS models."

    def handle(self, *args, **options):
        legacy_models = [
            model
            for model in apps.get_app_config("accounts").get_models()
            if not model._meta.managed
        ]

        if not legacy_models:
            self.stdout.write(self.style.WARNING("No unmanaged models found."))
            return

        created = 0
        skipped = 0

        with connection.schema_editor() as schema_editor:
            for model in legacy_models:
                table = model._meta.db_table
                if table in connection.introspection.table_names():
                    self.stdout.write(f"  {table} already exists — skipped")
                    skipped += 1
                    continue
                try:
                    schema_editor.create_model(model)
                    self.stdout.write(self.style.SUCCESS(f"  Created {table}"))
                    created += 1
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(f"  Failed to create {table}: {exc}")
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created}, skipped: {skipped}."
            )
        )
        self.stdout.write(
            "Import real data with: py manage.py import_mysql_dump "
            "(requires u673831287_hrms_final.sql in the project root)."
        )
