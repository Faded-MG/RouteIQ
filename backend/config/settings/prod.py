import os

from .base import *  # noqa: F403

DEBUG = False

secret_key = os.environ.get("DJANGO_SECRET_KEY", "")
if not secret_key or secret_key.startswith("insecure") or secret_key.startswith("django-insecure"):
    raise RuntimeError(
        "Refusing to start in production: DJANGO_SECRET_KEY is missing, empty, or insecure."
    )
SECRET_KEY = secret_key

app_contact = os.environ.get("APP_CONTACT", "")
if not app_contact or "example" in app_contact:
    raise RuntimeError(
        "Refusing to start in production: APP_CONTACT is required and must not be a placeholder."
    )
APP_CONTACT = app_contact

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "0") == "1"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Silenced checks for stateless REST API
SILENCED_SYSTEM_CHECKS = [
    "security.W002",  # XFrameOptionsMiddleware not needed for pure JSON API
    "security.W003",  # CsrfViewMiddleware not needed for stateless tokenless/sessionless API
]
