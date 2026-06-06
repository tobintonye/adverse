from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from security.models import CustomUser


def advertiser_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('security:login')
        if request.user.role != CustomUser.UserRole.ADVERTISER:
            messages.error(request, "You do not have access to this page.")
            return redirect('adverse:home')
        if not hasattr(request.user, 'advertiser_profile'):
            return redirect('advertiser:create_profile')
        return view_func(request, *args, **kwargs)
    return wrapper
