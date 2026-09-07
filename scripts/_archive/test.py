import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from allauth.socialaccount.providers.google.provider import GoogleProvider
from allauth.socialaccount.models import SocialApp
app = SocialApp(provider='google', client_id='1', secret='1')
p = GoogleProvider(None, app=app)
print(p.get_settings())
