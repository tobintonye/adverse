from django.shortcuts import render, redirect, get_object_or_404
from .forms import DeviceForm
from .models import Device, Admanager
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db import IntegrityError
from admanager.decorators import ad_manager_required

User = get_user_model()

@login_required
def DeviceList(request): 
    devices = Device.objects.all().order_by('-created_at')
    return render(request, 'devices/deviceList.html', {'devices':devices})

# simulating how we will register your billboard with our application.  device_id 
@login_required
@ad_manager_required
def RegisterDevice(request): 
   # print(f"User: {request.user}, Role: {getattr(request.user, 'role', 'No Role')}")
    if request.method == "POST":
        form = DeviceForm(request.POST or None)
        if form.is_valid():
            try: 
                device = form.save(commit=False)
                admanager_profile = Admanager.objects.get(user=request.user)
                device.device_owner = admanager_profile
                device.save()
                messages.success(request, "Device registered. Copy the device token into the Adverse app.") 
                return redirect("device:devicesList") # set for now
            except IntegrityError: 
                messages.error(request, "You have this device registered.")
                return redirect("device:devicesList") # set for now
    else:
        form = DeviceForm()
    return render (request, "devices/registerDevice.html", {"form": form})


# 