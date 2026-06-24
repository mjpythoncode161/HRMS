from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_employee_location_tracking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientVisitor",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        db_column="user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_visitors",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("emp_id", models.CharField(blank=True, max_length=255, null=True)),
                ("emp_name", models.CharField(blank=True, max_length=255, null=True)),
                ("client_name", models.CharField(max_length=255)),
                ("phone", models.CharField(blank=True, max_length=20, null=True)),
                ("location", models.CharField(blank=True, max_length=500, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                ("visit_date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "client_visitor",
                "ordering": ["-created_at"],
            },
        ),
    ]
