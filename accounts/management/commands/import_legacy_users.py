from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User
from accounts.models import Users
import csv
import os


class Command(BaseCommand):
    help = "Import legacy users from `users` table into Django's auth_user table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            help="Path to CSV report to write (default: legacy_user_migration_report.csv)",
            default="legacy_user_migration_report.csv",
        )

    def handle(self, *args, **options):
        report_path = options["report"]
        created = 0
        updated = 0
        skipped = 0
        rows = []

        legacy_users = Users.objects.all()
        if not legacy_users.exists():
            self.stdout.write(
                self.style.WARNING("No legacy users found (users table empty).")
            )
            return

        with transaction.atomic():
            for legacy in legacy_users:
                # Choose a username: prefer contact (phone), fall back to email, else legacy_{id}
                username = (legacy.contact or "").strip()
                if not username:
                    username = (legacy.email or "").split("@")[0]
                if not username:
                    username = f"legacy_{legacy.id}"

                # Ensure username uniqueness
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                # If a Django user with same email exists, update its fields instead of creating new
                django_user = None
                if legacy.email:
                    try:
                        django_user = User.objects.get(email=legacy.email)
                    except User.DoesNotExist:
                        django_user = None

                if django_user:
                    # Update basic fields
                    full = (legacy.full_name or "").strip()
                    parts = full.split(" ", 1)
                    first_name = parts[0] if parts else ""
                    last_name = parts[1] if len(parts) > 1 else ""
                    django_user.first_name = first_name
                    django_user.last_name = last_name
                    django_user.email = legacy.email or django_user.email
                    # Do NOT copy legacy MD5 password into Django's password field.
                    django_user.save()
                    updated += 1
                    rows.append(
                        (
                            legacy.id,
                            legacy.full_name,
                            legacy.email,
                            legacy.contact,
                            "updated",
                            django_user.username,
                        )
                    )
                    continue

                # Create new Django user with unusable password. Admin should send reset links.
                full = (legacy.full_name or "").strip()
                parts = full.split(" ", 1)
                first_name = parts[0] if parts else ""
                last_name = parts[1] if len(parts) > 1 else ""

                user = User(
                    username=username,
                    email=legacy.email or "",
                    first_name=first_name,
                    last_name=last_name,
                )
                user.set_unusable_password()
                user.save()
                created += 1
                rows.append(
                    (
                        legacy.id,
                        legacy.full_name,
                        legacy.email,
                        legacy.contact,
                        "created",
                        user.username,
                    )
                )

        # Write CSV report
        try:
            with open(report_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(
                    [
                        "legacy_id",
                        "full_name",
                        "email",
                        "contact",
                        "action",
                        "django_username",
                    ]
                )
                for r in rows:
                    writer.writerow(r)
            abs_path = os.path.abspath(report_path)
            self.stdout.write(self.style.SUCCESS(f"Report written to: {abs_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to write report: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Created: {created}, Updated: {updated}, Skipped: {skipped}"
            )
        )
