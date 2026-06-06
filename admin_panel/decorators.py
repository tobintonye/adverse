from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('security:login')
        if not (request.user.is_staff or request.user.role == 'admin'):
            messages.error(request, "You do not have access to this page.")
            return redirect('adverse:home')
        return view_func(request, *args, **kwargs)
    return wrapper
