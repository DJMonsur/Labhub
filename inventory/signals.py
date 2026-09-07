from allauth.socialaccount.signals import social_account_added, pre_social_login
from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.dispatch import receiver
from django.shortcuts import redirect
from .models import UserProfile


@receiver(pre_social_login)
def restrict_to_school_domain(sender, request, sociallogin, **kwargs):
    """Only allow school Google accounts.

    The domain comes from ALLOWED_EMAIL_DOMAIN in settings; set it to an empty
    string in .env to accept any Google account while testing.
    """
    domain = getattr(settings, 'ALLOWED_EMAIL_DOMAIN', '')
    if not domain:
        return
    email = sociallogin.account.extra_data.get('email', '')
    if not email.endswith(f'@{domain}'):
        raise ImmediateHttpResponse(redirect('/accounts/login/?error=domain'))

@receiver(social_account_added)
def assign_default_role(sender, request, sociallogin, **kwargs):
    user = sociallogin.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    if created:
        profile.role = 'student_teacher'
        profile.save()

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save

@receiver(user_logged_in)
def ensure_profile_exists(sender, user, request, **kwargs):
    profile, created = UserProfile.objects.get_or_create(user=user)
    if created:
        profile.role = 'student_teacher'
        profile.save()

@receiver(post_save, sender=UserProfile)
def sync_user_permissions(sender, instance, **kwargs):
    user = instance.user
    changed = False
    
    if instance.role in ['it_personnel', 'lab_personnel']:
        if not user.is_staff:
            user.is_staff = True
            changed = True
        
        # Give IT personnel superuser rights so they can manage everything
        if instance.role == 'it_personnel' and not user.is_superuser:
            user.is_superuser = True
            changed = True
        elif instance.role == 'lab_personnel' and user.is_superuser:
            user.is_superuser = False
            changed = True
            
    else: # student_teacher
        if user.is_staff or user.is_superuser:
            user.is_staff = False
            user.is_superuser = False
            changed = True
            
    if changed:
        user.save()