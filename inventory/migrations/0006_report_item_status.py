from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0005_sqlite_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowrequestitem',
            name='item_status',
            field=models.CharField(
                choices=[('ok', 'OK'), ('missing', 'Missing'), ('damaged', 'Damaged')],
                default='ok',
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_type', models.CharField(choices=[('weekly', 'Weekly'), ('daily', 'Daily'), ('monthly', 'Monthly'), ('yearly', 'Yearly'), ('custom', 'Custom')], max_length=10)),
                ('title', models.CharField(max_length=200)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('data', models.JSONField(default=dict)),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'report',
                'ordering': ['-generated_at'],
            },
        ),
    ]