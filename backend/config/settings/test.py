from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key-for-testing-only"

# Speed up testing password hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}
