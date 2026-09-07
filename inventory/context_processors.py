"""
Template context processors.

Exposes whether Google sign-in is actually configured, so templates can show
the Google button only when it will work, and fall back to username/password
otherwise. Without this, the sign-in page raises SocialApp.DoesNotExist on any
install that hasn't set up a Google Cloud project.
"""

from django.conf import settings


def auth_flags(request):
    return {
        'google_login_enabled': getattr(settings, 'GOOGLE_LOGIN_ENABLED', False),
    }
