from django.contrib import admin
from .models import UserProfile, BorrowRequest, BorrowRequestItem, Report


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at')
    list_editable = ('role',)
    list_filter = ('role',)
    search_fields = ('user__email', 'user__username')


class BorrowRequestItemInline(admin.TabularInline):
    model = BorrowRequestItem
    extra = 0
    readonly_fields = ('item', 'quantity')


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ('ref_number', 'borrower_name', 'section', 'teacher_name',
                    'role', 'status', 'is_signed', 'submitted_at')
    list_filter = ('status', 'role', 'is_signed')
    search_fields = ('ref_number', 'borrower_name', 'teacher_name', 'section')
    readonly_fields = ('ref_number', 'submitted_at')
    inlines = [BorrowRequestItemInline]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'start_date', 'end_date', 'generated_at')
    list_filter = ('report_type',)
    search_fields = ('title',)
    readonly_fields = ('data', 'generated_at')
