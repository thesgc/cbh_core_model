# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cbh_core_model', '0011_auto_20150831_0618'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='dataformconfig',
            options={'ordering': ('l0', 'l1', 'l2', 'l3', 'l4')},
        ),
    ]
