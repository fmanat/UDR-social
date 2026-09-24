"""Point d'entrée gunicorn : `gunicorn service.wsgi:app`."""

from service.app import create_app

app = create_app()
