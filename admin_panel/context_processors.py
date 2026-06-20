from adverse.models import Message

def unread_messages_count(request):
    if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        try:
            count = Message.objects.filter(is_read=False).count()
            return {'unread_messages_count': count}
        except Exception:
            pass
    return {'unread_messages_count': 0}
