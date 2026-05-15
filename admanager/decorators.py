from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from security.models import CustomUser
def ad_manager_required(view_func): 
    @wraps(view_func)
    def wrapper(request, *agrs, **kwargs):
        if not request.user.is_authenticated:
            return redirect('security:login')
        if request.user.role != CustomUser.UserRole.AD_MANAGER: 
            messages.error(request, "You have no access to this page")
            return redirect("adverse:home") # set for now
        if not hasattr(request.user, 'ad_manager'):
            messages.error(request, 'Please create a profile')
            return redirect('admanager:profile')
        return view_func(request, *agrs, **kwargs)
    return wrapper