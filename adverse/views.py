from django.shortcuts import render
from django.http import JsonResponse
from .models import Message

def home(request):
    return render(request, 'adverse/home.html')

def about(request):
    return render(request, 'adverse/about.html')

def how_it_works(request):
    return render(request, 'adverse/how_it_works.html')

def contact(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        company = request.POST.get('company', '').strip()
        email = request.POST.get('email', '').strip()
        message_text = request.POST.get('message', '').strip()

        if not full_name or not email or not message_text:
            return JsonResponse({'status': 'error', 'message': 'Required fields are missing.'}, status=400)

        # Save to database
        Message.objects.create(
            full_name=full_name,
            company=company,
            email=email,
            message=message_text
        )
        return JsonResponse({'status': 'success'})

    return render(request, 'adverse/contact.html')

def terms(request):
    return render(request, 'adverse/terms.html')

def privacy(request):
    return render(request, 'adverse/privacy.html')