import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from django.test import Client
c = Client()
res = c.get('/')
print(res.status_code)
if res.status_code == 200:
    print(res.content.decode('utf-8')[:200])
else:
    print("Error:", res.content)
