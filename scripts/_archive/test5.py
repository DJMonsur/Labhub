import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from django.test import Client
c = Client()
res = c.get('/accounts/google/login/')
print(res.content.decode('utf-8'))
