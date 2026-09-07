from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'created_at')
    list_editable = ('role',)
    list_filter = ('role',)
    search_fields = ('user__email', 'user__username')
