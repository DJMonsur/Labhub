"""
seed_demo — get a fresh database from empty to usable in one command.

Reads the real inventory out of biology_lab_lims.sql (so the data is the actual
lab catalogue, not invented placeholders), then creates one login account per
role so you can sign in immediately without setting up Google OAuth.

    python manage.py seed_demo

Safe to re-run: it skips anything that already exists and never deletes.
"""

import re
from pathlib import Path

from decouple import config
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.models import (Item, ItemType, InventoryRecord, LimsUser,
                              Location, UserProfile)


# Accounts created for you. Passwords are intentionally simple — this is a
# local development convenience, not a production credential set.
DEMO_ACCOUNTS = [
    ('labstaff', 'labpass123', 'lab_personnel',   'Lab Personnel',    'admin@pshs-carc.edu.ph'),
    ('itstaff',  'itpass123',  'it_personnel',    'IT Personnel',     'it@pshs-carc.edu.ph'),
    ('student',  'studpass123', 'student_teacher', 'Sample Student',  'student@pshs-carc.edu.ph'),
]


def _split_values(block: str):
    """Split a SQL VALUES block into rows, respecting quotes and parentheses."""
    rows, buf, depth, in_str, esc = [], '', 0, False, False
    for ch in block:
        if esc:
            buf += ch
            esc = False
            continue
        if ch == '\\':
            buf += ch
            esc = True
            continue
        if ch == "'":
            in_str = not in_str
            buf += ch
            continue
        if not in_str:
            if ch == '(':
                depth += 1
                if depth == 1:
                    buf = ''
                    continue
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    rows.append(buf)
                    buf = ''
                    continue
        if depth >= 1:
            buf += ch
    return rows


def _split_fields(row: str):
    """Split one row into its individual column values."""
    out, buf, in_str, esc = [], '', False, False
    for ch in row:
        if esc:
            buf += ch
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == "'":
            in_str = not in_str
            continue
        if ch == ',' and not in_str:
            out.append(buf.strip())
            buf = ''
            continue
        buf += ch
    out.append(buf.strip())
    return [None if v.upper() == 'NULL' else v for v in out]


def _extract(sql: str, table: str):
    """Pull the rows from `INSERT INTO <table> (...) VALUES (...), (...);`"""
    match = re.search(
        rf'INSERT\s+INTO\s+`?{table}`?\s*\([^)]*\)\s*VALUES(.*?);',
        sql, re.S | re.I,
    )
    if not match:
        return []
    body = re.sub(r'--[^\n]*', '', match.group(1))   # strip SQL comments
    return [_split_fields(r) for r in _split_values(body)]


class Command(BaseCommand):
    help = 'Load the lab inventory and create demo login accounts.'

    def handle(self, *args, **options):
        # Fast path: already seeded. Keeps the Vercel build step cheap too —
        # every deploy runs seed_demo, so this turns hundreds of inserts into
        # one COUNT query once the database is populated.
        if Item.objects.exists():
            self.stdout.write(self.style.SUCCESS(
                f'  Database already seeded ({Item.objects.count()} items) — nothing to do.'))
            return

        sql_path = Path(settings.BASE_DIR) / 'biology_lab_lims.sql'
        if not sql_path.exists():
            self.stderr.write(self.style.ERROR(
                f'Could not find {sql_path.name}. It should sit next to manage.py.'))
            return

        sql = sql_path.read_text(encoding='utf-8', errors='replace')

        # The demo accounts (labpass123, ...) are a local-dev convenience, not
        # production credentials. Only create them in development, or when
        # explicitly asked with SEED_DEMO_ACCOUNTS=true in production.
        allow_demo_accounts = settings.DEBUG or config(
            'SEED_DEMO_ACCOUNTS', default=False, cast=bool)

        with transaction.atomic():
            self._seed_locations(sql)
            self._seed_types(sql)
            self._seed_lims_users(sql)
            self._seed_items(sql)
            if allow_demo_accounts:
                self._seed_accounts()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('  Database ready.'))
        self.stdout.write('')
        if allow_demo_accounts:
            self.stdout.write('  Sign in with any of these:')
            self.stdout.write('')
            for username, password, role, *_ in DEMO_ACCOUNTS:
                label = dict(UserProfile.ROLE_CHOICES).get(role, role)
                self.stdout.write(f'     {username:<10} / {password:<13} {label}')
        else:
            self.stdout.write('  Demo login accounts skipped (production mode).')
            self.stdout.write('  Set SEED_DEMO_ACCOUNTS=true to create them, or use')
            self.stdout.write('  python manage.py createsuperuser for a real account.')
        self.stdout.write('')

    # ── individual tables ────────────────────────────────────────────────────
    def _seed_locations(self, sql):
        rows = _extract(sql, 'location')
        made = 0
        for name, building, room in rows:
            _, created = Location.objects.get_or_create(
                location_name=name,
                defaults={'building': building, 'room_code': room},
            )
            made += created
        self.stdout.write(f'  locations      {made} added, {len(rows) - made} already there')

    def _seed_types(self, sql):
        rows = _extract(sql, 'item_type')
        made = 0
        for label, category in rows:
            _, created = ItemType.objects.get_or_create(
                type_label=label, defaults={'category': category})
            made += created
        self.stdout.write(f'  item types     {made} added, {len(rows) - made} already there')

    def _seed_lims_users(self, sql):
        """The legacy `user` table. Dashboard logging joins against it."""
        rows = _extract(sql, 'user')
        made = 0
        for name, email, role, _hash in rows:
            _, created = LimsUser.objects.get_or_create(
                user_email=email,
                defaults={
                    'user_name': name,
                    'user_role': role,
                    # Never a usable credential — this table is for audit joins,
                    # authentication goes through Django's own User model.
                    'password_hash': '!unusable',
                    'created_at': timezone.now(),
                },
            )
            made += created
        self.stdout.write(f'  lab users      {made} added, {len(rows) - made} already there')

    def _seed_items(self, sql):
        rows = _extract(sql, 'item')
        types = {t.type_id: t for t in ItemType.objects.all()}
        location = Location.objects.first()
        made = skipped = 0

        for row in rows:
            if len(row) < 4:
                continue
            name, type_id, count, unit = row[0], row[1], row[2], row[3]
            try:
                item_type = types.get(int(type_id))
            except (TypeError, ValueError):
                item_type = None
            if item_type is None:
                skipped += 1
                continue

            item, created = Item.objects.get_or_create(
                item_name=name,
                defaults={
                    'type': item_type,
                    'item_count': int(count or 0),
                    'unit': unit,
                    'is_borrowable': True,
                    'is_visible': True,
                },
            )
            made += created

            # Mirror the SQL file's behaviour: stock starts fully available.
            if location:
                InventoryRecord.objects.get_or_create(
                    item=item, location=location,
                    defaults={'available_count': item.item_count},
                )

        note = f', {skipped} skipped (unknown type)' if skipped else ''
        self.stdout.write(f'  items          {made} added, {len(rows) - made - skipped} already there{note}')

    def _seed_accounts(self):
        made = 0
        for username, password, role, full_name, email in DEMO_ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': full_name},
            )
            if created:
                user.set_password(password)
                user.save()
                made += 1
            # The post_save signal on UserProfile syncs is_staff/is_superuser.
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.role != role:
                profile.role = role
                profile.save()
        self.stdout.write(f'  accounts       {made} added, {len(DEMO_ACCOUNTS) - made} already there')
