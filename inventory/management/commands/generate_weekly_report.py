"""
generate_weekly_report — save a report for the current week (Mon → today).

Run on a scheduler (cron / Railway cron / Windows Task Scheduler) to
auto-generate the weekly report. Idempotent per call; each run saves a
fresh Report row.

    python manage.py generate_weekly_report
"""

from django.core.management.base import BaseCommand

from inventory.models import Report
from inventory.reports import _period_for, generate_report_data, build_report_title


class Command(BaseCommand):
    help = 'Auto-generate the weekly report (Mon → today) and save it.'

    def handle(self, *args, **options):
        start, end = _period_for('weekly')
        data = generate_report_data(start, end)
        report = Report.objects.create(
            report_type='weekly',
            title=build_report_title('weekly'),
            start_date=start,
            end_date=end,
            data=data,
        )
        totals = data['totals']
        self.stdout.write(self.style.SUCCESS(
            f'Saved weekly report #{report.pk} '
            f'({start} → {end}) — '
            f'borrowed {totals["borrowed_qty"]}, '
            f'missing {totals["missing_qty"]}, '
            f'damaged {totals["damaged_qty"]}, '
            f'added {totals["added_qty"]}.'
        ))