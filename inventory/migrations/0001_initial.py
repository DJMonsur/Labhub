from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        # ── BorrowRequest ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='BorrowRequest',
            fields=[
                ('id',            models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_number',    models.CharField(max_length=20, unique=True)),
                ('borrower_name', models.CharField(max_length=100)),
                ('section',       models.CharField(max_length=100)),
                ('teacher_name',  models.CharField(max_length=100)),
                ('role',          models.CharField(max_length=30)),
                ('purpose',       models.CharField(max_length=300)),
                ('date_needed',   models.DateTimeField()),
                ('return_date',   models.DateField()),
                ('notes',         models.TextField(blank=True, default='')),
                ('status',        models.CharField(default='pending', max_length=20)),
                ('submitted_at',  models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'borrow_request',
                'ordering': ['-submitted_at'],
            },
        ),
        # ── BorrowRequestItem ──────────────────────────────────────────────
        migrations.CreateModel(
            name='BorrowRequestItem',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                # item_id references the unmanaged 'item' table
                ('item_id',  models.IntegerField(db_column='item_id')),
                ('quantity', models.IntegerField()),
                ('borrow_request', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='inventory.borrowrequest',
                )),
            ],
            options={
                'db_table': 'borrow_request_item',
            },
        ),
    ]
