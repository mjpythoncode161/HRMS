from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_clientvisitor"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientvisitor",
            name="photo",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="visitor_photos/",
            ),
        ),
    ]
