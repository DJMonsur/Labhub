import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from django.contrib.sites.models import Site
print(Site.objects.get(id=1).domain)
