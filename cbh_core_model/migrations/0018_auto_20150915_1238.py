# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def create_data_types(apps, schema_editor):

    DataType = apps.get_model("cbh_core_model", "DataType")
    DataType.objects.get_or_create(name="Project")
    DataType.objects.get_or_create(name="Sub-Project")
    DataType.objects.get_or_create(name="Assay")
    DataType.objects.get_or_create(name="Activity")
    DataType.objects.get_or_create(name="Study")
    ProjectType = apps.get_model("cbh_core_model", "ProjectType")
    ProjectType.objects.get_or_create(name="chemical")
    ProjectType.objects.get_or_create(name="assay")
    ProjectType.objects.get_or_create(name="inventory")


class Migration(migrations.Migration):

    dependencies = [
        ('cbh_core_model', '0017_auto_20150915_0022'),
    ]

    operations = [
        migrations.RunPython(create_data_types),
    ]
