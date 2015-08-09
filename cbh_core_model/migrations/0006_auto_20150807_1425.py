# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def create_data_types(apps, schema_editor):
    
    DataType = apps.get_model("cbh_core_model", "DataType")
    DataType.objects.create(name="Assay")
    DataType.objects.create(name="Activity")


class Migration(migrations.Migration):

    dependencies = [
        ('cbh_core_model', '0005_auto_20150807_1425'),
    ]



    operations = [
        migrations.RunPython(create_data_types),
    ]

