"""
inventory/models.py

Django ORM models that map 1-to-1 onto the tables created by
biology_lab_lims.sql.  The db_table Meta option keeps the table
names exactly as the SQL file defines them so Django can read the
already-seeded data without any renaming.

Two extra tables (BorrowRequest, BorrowRequestItem) are added here
for the frontend borrow form — they are NOT in the original SQL and
will be created by Django migrations.

CHANGES vs v1:
  - Item: added is_visible = BooleanField(default=True)
  - BorrowRequest: added 'returned' to STATUS_CHOICES
"""

from django.db import models
from django.contrib.auth.models import User


#—————USER-ROLES————————————————————————————————————————
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student_teacher', 'Student / Teacher'),
        ('lab_personnel',   'Lab Personnel'),
        ('it_personnel',    'IT Personnel'),
    ]
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student_teacher')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_profile'

    def __str__(self):
        return f'{self.user.email} — {self.role}'

# ─── 1. LOCATION ─────────────────────────────────────────────────────────────
class Location(models.Model):
    location_id   = models.AutoField(primary_key=True)
    location_name = models.CharField(max_length=120)
    building      = models.CharField(max_length=80, null=True, blank=True)
    room_code     = models.CharField(max_length=30, null=True, blank=True)

    class Meta:
        db_table = 'location'
        managed  = False   # table already created by the SQL file

    def __str__(self):
        return self.location_name


# ─── 2. ITEM_TYPE ─────────────────────────────────────────────────────────────
class ItemType(models.Model):
    type_id    = models.SmallAutoField(primary_key=True)
    type_label = models.CharField(max_length=60, unique=True)
    category   = models.CharField(max_length=40)   # Equipment | Material | Slide

    class Meta:
        db_table = 'item_type'
        managed  = False

    def __str__(self):
        return self.type_label


# ─── 3. LIMS USER ─────────────────────────────────────────────────────────────
class LimsUser(models.Model):
    ROLE_CHOICES = [
        ('student',       'Student'),
        ('teacher',       'Teacher'),
        ('lab_personnel', 'Lab Personnel'),
        ('it_personnel',  'IT Personnel'),
    ]
    user_id       = models.AutoField(primary_key=True)
    user_name     = models.CharField(max_length=100)
    user_email    = models.EmailField(max_length=150, unique=True)
    user_role     = models.CharField(max_length=20, choices=ROLE_CHOICES)
    password_hash = models.CharField(max_length=255)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user'
        managed  = False

    def __str__(self):
        return f'{self.user_name} ({self.user_role})'


# ─── 4. ITEM ──────────────────────────────────────────────────────────────────
class Item(models.Model):
    item_id          = models.AutoField(primary_key=True)
    item_name        = models.CharField(max_length=200)
    type             = models.ForeignKey(
                           ItemType,
                           on_delete=models.RESTRICT,
                           db_column='type_id',
                           related_name='items',
                       )
    item_count       = models.IntegerField(default=0)
    unit             = models.CharField(max_length=20, null=True, blank=True)
    item_description = models.TextField(null=True, blank=True)
    is_borrowable    = models.BooleanField(default=True)
    is_visible       = models.BooleanField(default=True)   # ← added in migration 0002

    class Meta:
        db_table = 'item'
        managed  = False   # schema managed by SQL + RunPython migration

    def __str__(self):
        return self.item_name


# ─── 5. INVENTORY_RECORD ──────────────────────────────────────────────────────
class InventoryRecord(models.Model):
    record_id       = models.AutoField(primary_key=True)
    item            = models.ForeignKey(
                          Item,
                          on_delete=models.CASCADE,
                          db_column='item_id',
                          related_name='inventory_records',
                      )
    location        = models.ForeignKey(
                          Location,
                          on_delete=models.RESTRICT,
                          db_column='location_id',
                      )
    available_count = models.IntegerField(default=0)
    last_updated    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'inventory_record'
        managed         = False
        unique_together = (('item', 'location'),)

    def __str__(self):
        return (
            f'{self.item.item_name} @ {self.location.location_name} '
            f'({self.available_count} available)'
        )


# ─── 6. BORROW_RECORD (from the original SQL schema) ─────────────────────────
class BorrowRecord(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('borrowed',  'Borrowed'),
        ('returned',  'Returned'),
        ('cancelled', 'Cancelled'),
    ]
    borrow_id         = models.AutoField(primary_key=True)
    user              = models.ForeignKey(
                            LimsUser,
                            on_delete=models.RESTRICT,
                            db_column='user_id',
                        )
    item              = models.ForeignKey(
                            Item,
                            on_delete=models.RESTRICT,
                            db_column='item_id',
                        )
    location          = models.ForeignKey(
                            Location,
                            on_delete=models.RESTRICT,
                            db_column='location_id',
                        )
    quantity_borrowed = models.IntegerField(default=1)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    borrow_date       = models.DateTimeField(null=True, blank=True)
    return_date       = models.DateTimeField(null=True, blank=True)
    due_date          = models.DateField(null=True, blank=True)
    notes             = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'borrow_record'
        managed  = False

    def __str__(self):
        return f'Borrow #{self.borrow_id} — {self.item.item_name} ({self.status})'


# ─── 7. INVENTORY_LOG ─────────────────────────────────────────────────────────
class InventoryLog(models.Model):
    log_id      = models.AutoField(primary_key=True)
    user        = models.ForeignKey(
                      LimsUser,
                      on_delete=models.RESTRICT,
                      db_column='user_id',
                  )
    item        = models.ForeignKey(
                      Item,
                      on_delete=models.CASCADE,
                      db_column='item_id',
                  )
    action_type = models.CharField(max_length=30)
    old_value   = models.TextField(null=True, blank=True)
    new_value   = models.TextField(null=True, blank=True)
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_log'
        managed  = False

    def __str__(self):
        return f'Log #{self.log_id} — {self.action_type} on {self.item.item_name}'


# ─────────────────────────────────────────────────────────────────────────────
#  BORROW REQUEST TABLES  (added by Django — not in the original SQL)
#  These store the web form submissions from students/teachers.
# ─────────────────────────────────────────────────────────────────────────────

class BorrowRequest(models.Model):
    """One submission from the borrowing form (may contain multiple items)."""
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('returned',  'Returned'),   # ← added; lab personnel marks items back
        ('cancelled', 'Cancelled'),
    ]
    ROLE_CHOICES = [
        ('Student',       'Student'),
        ('Teacher',       'Teacher'),
        ('Lab Personnel', 'Lab Personnel'),
    ]
    ref_number    = models.CharField(max_length=20, unique=True)
    borrower_name = models.CharField(max_length=100)
    section       = models.CharField(max_length=100)
    teacher_name  = models.CharField(max_length=100)
    role          = models.CharField(max_length=30, choices=ROLE_CHOICES)
    purpose       = models.CharField(max_length=300)
    date_needed   = models.DateTimeField()
    return_date   = models.DateField()
    notes         = models.TextField(blank=True, default='')
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_signed     = models.BooleanField(default=False)
    submitted_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'borrow_request'
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.ref_number} — {self.borrower_name} ({self.status})'


class BorrowRequestItem(models.Model):
    borrow_request = models.ForeignKey(
                         BorrowRequest,
                         on_delete=models.CASCADE,
                         related_name='items',
                     )
    item           = models.ForeignKey(
                         Item,
                         on_delete=models.RESTRICT,
                         db_column='item_id',
                     )
    quantity       = models.IntegerField()

    class Meta:
        db_table = 'borrow_request_item'

    def __str__(self):
        return (
            f'{self.borrow_request.ref_number} — '
            f'{self.item.item_name} × {self.quantity}'
        )
