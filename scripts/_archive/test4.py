import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from django.test import Client
c = Client()
res = c.get('/accounts/google/login/')
print("GET status:", res.status_code)
if res.status_code == 302:
    print("GET redirect:", res.url)
