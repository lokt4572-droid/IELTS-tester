from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0002_chatmessage_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="model",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
