from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("listening", "0002_listeninganswer_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="listeningattempt",
            name="exam_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
