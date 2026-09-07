import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()
from django.template import Context, Template
from django.test import RequestFactory
t = Template("{% load socialaccount %}{% provider_login_url 'google' process='login' action='reauthenticate' %}")
c = Context({'request': RequestFactory().get('/')})
print(t.render(c))
