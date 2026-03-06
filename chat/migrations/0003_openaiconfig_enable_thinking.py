# Generated manually for enable_thinking feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_openaiconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='openaiconfig',
            name='enable_thinking',
            field=models.BooleanField(default=True, help_text='Enable thinking status messages to users during processing'),
        ),
    ]
