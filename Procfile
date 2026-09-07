web: gunicorn lims_project.wsgi --bind 0.0.0.0:$PORT --workers 3 --timeout 60
release: python manage.py migrate --noinput
