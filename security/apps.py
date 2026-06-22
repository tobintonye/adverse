from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = 'security'
    
    def ready(self):
        import security.signals  # noqa