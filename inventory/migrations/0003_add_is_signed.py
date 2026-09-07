"""
0003_add_is_signed.py

Adds is_signed BOOLEAN to borrow_request.

This flag is independent of `status` and represents whether the lab
personnel has physically received the borrower's signed paper form.
It is set manually from the dashboard and has no effect on inventory
counts or borrow status — purely a record-keeping checkbox.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_add_is_visible'),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowrequest',
            name='is_signed',
            field=models.BooleanField(default=False),
        ),
    ]
