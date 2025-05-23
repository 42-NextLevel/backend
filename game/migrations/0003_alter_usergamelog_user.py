# Generated by Django 5.1.1 on 2024-11-05 07:17

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_alter_user_profile_image'),
        ('game', '0002_alter_gamelog_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usergamelog',
            name='user',
            field=models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, to='api.user'),
        ),
    ]
