try:
    from .celery import app as celery_app
    __all__ = ("celery_app",)  # starts when django boots
except ImportError:
    pass  # celery not installed — background tasks disabled (fine for local preview)