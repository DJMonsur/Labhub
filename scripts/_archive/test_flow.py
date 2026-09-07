import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lims_project.settings')
django.setup()

from django.test import Client
c = Client(SERVER_NAME='127.0.0.1:8000')

# 1. Check if allauth migrations are applied
from django.db import connection
cursor = connection.cursor()
cursor.execute("SHOW TABLES LIKE '%socialaccount%'")
tables = cursor.fetchall()
print("=== Social account tables ===")
for t in tables: print(" ", t[0])

cursor.execute("SHOW TABLES LIKE '%account_%'")
tables = cursor.fetchall()
print("\n=== Account tables ===")
for t in tables: print(" ", t[0])

# 2. Check django_site
from django.contrib.sites.models import Site
site = Site.objects.get(id=1)
print(f"\n=== Site (id=1) ===")
print(f"  domain: {site.domain}")
print(f"  name: {site.name}")

# 3. Check if SocialApp exists in DB
from allauth.socialaccount.models import SocialApp
apps = SocialApp.objects.all()
print(f"\n=== SocialApps in DB ===")
if apps:
    for a in apps:
        print(f"  provider={a.provider} client_id={a.client_id[:20]}...")
else:
    print("  NONE! (allauth is reading from settings.py APP config instead)")

# 4. Simulate the actual POST to google login
print("\n=== Simulating POST to /accounts/google/login/?process=login ===")
res = c.post('/accounts/google/login/?process=login')
print(f"  Status: {res.status_code}")
if res.status_code == 302:
    url = res.url
    print(f"  Redirect URL: {url[:100]}...")
    if 'prompt=' in url:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        print(f"  prompt param: {params.get('prompt')}")
        print(f"  redirect_uri param: {params.get('redirect_uri')}")
        print(f"  scope param: {params.get('scope')}")
    else:
        print("  WARNING: No prompt param in redirect URL!")
elif res.status_code == 200:
    content = res.content.decode()
    print(f"  Got 200 instead of redirect! First 300 chars:")
    print(f"  {content[:300]}")
else:
    print(f"  Unexpected status! Content: {res.content.decode()[:300]}")

# 5. Check callback URL
from django.urls import reverse
try:
    cb = reverse('google_callback')
    print(f"\n=== Callback URL ===")
    print(f"  {cb}")
except:
    try:
        cb = reverse('google_login')
        print(f"\n=== Google login URL ===")
        print(f"  {cb}")
    except Exception as e:
        print(f"\n=== URL resolve error: {e}")
