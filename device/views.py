from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from admanager.decorators import ad_manager_required
from device.models import Billboard, PlayerDevice
from .forms import BillboardForm
from scheduling.models import TimeSlot, BillboardCapacity

@login_required(login_url='security:login')
@ad_manager_required
def billboard_list(request):
    ad_manager = request.user.ad_manager
    billboards = Billboard.objects.filter(ad_manager=ad_manager).order_by('-created_at')

    search_query = request.GET.get('search', '').strip()
    if search_query:
        billboards = billboards.filter(
            Q(name__icontains=search_query) | Q(location_name__icontains=search_query)
        )

    selected_availability = request.GET.get('availability', '').strip()
    if selected_availability:
        billboards = billboards.filter(availability=selected_availability)

    selected_screen_type = request.GET.get('screen_type', '').strip()
    if selected_screen_type:
        billboards = billboards.filter(screen_type=selected_screen_type)

    selected_state = request.GET.get('state', '').strip()
    if selected_state:
        billboards = billboards.filter(state=selected_state)

    # Distinct states this manager actually has billboards in — populates the filter dropdown
    states = (
        Billboard.objects.filter(ad_manager=ad_manager)
        .exclude(state='')
        .values_list('state', flat=True)
        .distinct()
        .order_by('state')
    )

    context = {
        "billboards": billboards,
        "search_query": search_query,
        "selected_availability": selected_availability,
        "selected_screen_type": selected_screen_type,
        "selected_state": selected_state,
        "states": states,
    }
    return render(request, "adManager/billboard_list.html", context)


@login_required(login_url='security:login')
@ad_manager_required
def billboard_create(request):
    ad_manager = request.user.ad_manager

    if ad_manager.verification_status == ad_manager.VerificationStatus.SUSPENDED:
        messages.error(request, "Suspended accounts cannot add billboards.")
        return redirect("device:billboard_list")

    if request.method == "POST":
        form = BillboardForm(request.POST, request.FILES)
        if form.is_valid():
            billboard = form.save(commit=False)
            billboard.ad_manager = ad_manager
            billboard.save()
            messages.success(request, f"Billboard '{billboard.name}' created successfully.")
            return redirect("device:billboard_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.error(request, error)
                    else:
                        label = form.fields[field].label or field.replace('_', ' ').capitalize()
                        messages.error(request, f"{label}: {error}")
    else:
        form = BillboardForm()

    context = {
        "form": form,
        "action": "Add",
        "billboard": None,
    }
    return render(request, "adManager/billboard_create.html", context)


@login_required(login_url='security:login')
@ad_manager_required
def billboard_edit(request, pk):
    ad_manager = request.user.ad_manager
    billboard = get_object_or_404(Billboard, pk=pk, ad_manager=ad_manager)

    if ad_manager.verification_status == ad_manager.VerificationStatus.SUSPENDED:
        messages.error(request, "Suspended accounts cannot edit billboards.")
        return redirect("device:billboard_list")

    if request.method == "POST":
        form = BillboardForm(request.POST, request.FILES, instance=billboard)
        if form.is_valid():
            form.save()
            messages.success(request, f"Billboard '{billboard.name}' updated successfully.")
            return redirect("device:billboard_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    label = form.fields[field].label or field.replace('_', ' ').capitalize()
                    messages.error(request, f"{label}: {error}")
    else:
        form = BillboardForm(instance=billboard)

    context = {
        "form": form,
        "action": "Edit",
        "billboard": billboard,
    }
    return render(request, "adManager/billboard_edit.html", context)

@login_required(login_url='security:login')
@ad_manager_required
def billboard_schedule(request, pk):
    """
    Shows what's scheduled to play on this billboard — defaults to today,
    but accepts ?date=YYYY-MM-DD to look at any other day.
    """
    ad_manager = request.user.ad_manager
    billboard = get_object_or_404(Billboard, pk=pk, ad_manager=ad_manager)

    # Which date are we viewing? 
    date_param = request.GET.get("date", "").strip()
    today = timezone.now().date()
    if date_param:
        try:
            from datetime import datetime
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            target_date = today
    else:
        target_date = today
    
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    #  Capacity for this billboard
    try:
        capacity = billboard.capacity
        max_slots_per_day = capacity.max_slots_per_day
    except BillboardCapacity.DoesNotExist:
        capacity = None
        max_slots_per_day = 0

    #  The actual playlist for the selected date
    time_slots  = ( TimeSlot.objects.filter(billboard=billboard, date=target_date, is_active=True,).select_related("campaign", "campaign__media", "campaign__advertiser", "campaign_slot").order_by("play_order"))
    booked_count = time_slots.count()
    free_count = max(0, max_slots_per_day - booked_count)
    context = {
        "billboard": billboard,
        "time_slots": time_slots,
        "target_date": target_date,
        "prev_date": prev_date,
        "next_date": next_date,
        "is_today": target_date == today,
        "max_slots_per_day": max_slots_per_day,
        "booked_count": booked_count,
        "free_count": free_count,
        "has_capacity_set": capacity is not None,
    }
    return render(request, "adManager/billboard_schedule.html", context)

# Device pairing
@login_required(login_url='security:login')
@ad_manager_required
def device_pair(request):
    """
    Ad manager enters the pairing code shown on the Android box's screen,
    selects which billboard to assign it to.
    """
    ad_manager = request.user.ad_manager

    # Clear stale messages from other pages on a fresh GET visit
    if request.method == "GET":
        storage = messages.get_messages(request)
        storage.used = True

    available_billboards = Billboard.objects.filter(ad_manager=ad_manager).exclude(
        player_device__status__in=[
            PlayerDevice.Status.PENDING,
            PlayerDevice.Status.ACTIVE,
            PlayerDevice.Status.OFFLINE,
        ]
    )

    if request.method == "POST":
        pairing_code = request.POST.get("pairing_code", "").strip().upper()
        billboard_id = request.POST.get("billboard_id", "").strip()

        # DEBUG — remove once confirmed working
        print(f"[device_pair] raw POST data: {dict(request.POST)}")
        print(f"[device_pair] parsed pairing_code={pairing_code!r} billboard_id={billboard_id!r}")

        if not pairing_code:
            messages.error(request, "Please enter the pairing code shown on the device.")
            return redirect("device:device_pair")

        if not billboard_id:
            messages.error(request, "Please select a billboard to pair this device to.")
            return redirect("device:device_pair")

        try:
            player = PlayerDevice.objects.get(pairing_code=pairing_code)
        except PlayerDevice.DoesNotExist:
            messages.error(request, "Invalid pairing code. Double-check the code shown on the device.")
            return redirect("device:device_pair")

        if player.status == PlayerDevice.Status.DISABLED:
            messages.error(request, "This device has been disabled and cannot be paired.")
            return redirect("device:device_pair")

        billboard = get_object_or_404(Billboard, pk=billboard_id, ad_manager=ad_manager)

        if billboard.is_paired:
            existing = billboard.player_device
            if existing.status != PlayerDevice.Status.DISABLED:
                messages.error(
                    request,
                    f"'{billboard.name}' already has an active device paired. Disable it first.",
                )
                return redirect("device:device_pair")

        player.pair_to_billboard(billboard)
        messages.success(
            request,
            f"Device paired to '{billboard.name}'. It will come online once it sends its first heartbeat.",
        )
        return redirect("device:billboard_list")

    context = {
        "available_billboards": available_billboards,
    }
    return render(request, "adManager/device_pair.html", context)

@login_required(login_url='security:login')
@ad_manager_required
def device_detail(request, pk):
    """
    Status page for a paired device — online/offline, last heartbeat,
    firmware version. Also offers unpair/disable actions.
    """
    ad_manager = request.user.ad_manager
    billboard = get_object_or_404(Billboard, pk=pk, ad_manager=ad_manager)

    if not billboard.is_paired:
        messages.info(request, f"'{billboard.name}' has no device paired yet.")
        return redirect("device:device_pair")
    
    player = billboard.player_device
    
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "unpair":
            player.unpair()
            messages.success(
                request,
                f"Device unpaired from '{billboard.name}'. "
                f"The billboard is now available for a new device to be paired.",
            )
            return redirect("device:billboard_list")
        elif action == "disable":
            player.disable()
            messages.success(request, f"Device unpaired from '{billboard.name}' and disabled.")
            return redirect("device:billboard_list")
        elif action == "rotate_token": 
            player.rotate_token()
            messages.success(request, "Device auth token rotated. The device will need to re-authenticate.")
            return redirect("device:device_detail", pk=billboard.pk)
    
    context = {
        "billboard": billboard,
        "player": player,
    }

    return render(request, "adManager/device_detail.html", context)
