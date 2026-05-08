from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from .models import Admanager
from .forms import AdManagerProfileForm
from security.models import CustomUser
from django.contrib import messages
from functools import wraps
from django.contrib.auth.decorators import login_required

User = get_user_model()

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
            return redirect('admanager:setup_profile')
        return view_func(request, *agrs, **kwargs)
    return wrapper

@login_required(login_url='security:login')
def adManagerProfile(request):
    if hasattr(request.user, 'ad_manager'):
        messages.info(request, "Your profile already exists.")  # set for now 
        return redirect("adverse:home")

    if request.method == "POST": 
        form = AdManagerProfileForm(request.POST)
        if form.is_valid(): 
            admanagerProfile =  form.save(commit=False)
            admanagerProfile.user = request.user
            admanagerProfile.save()
            messages.success(request, "Your account has been created!")
            return redirect("adverse:home") # set for now
    else: 
        form = AdManagerProfileForm()
    return render(request, "adManager/profile.html", {"form": form}) 

@login_required(login_url='security:login')
@ad_manager_required
def adManagerDashboard(request): 
    return render(request, 'adManager/dashboard.html')