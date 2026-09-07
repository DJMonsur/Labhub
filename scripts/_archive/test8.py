import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from django.test import Client
c = Client()
res = c.post('/accounts/google/login/?process=login&action=reauthenticate')
print(res.url)
