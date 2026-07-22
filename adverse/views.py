from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .forms import ContactForm


def home(request):
    return render (request, 'adverse/home.html')

def about(request):
    return render(request, 'adverse/about.html')

def how_it_works(request):
    return render(request, 'adverse/how_it_works.html')

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_msg = form.save()
    
            subject = f"[Advers Contact] New message from {contact_msg.name} ({contact_msg.role})"
            body = (
                f"Name: {contact_msg.name}\n"
                f"Email: {contact_msg.email}\n"
                f"Role: {contact_msg.role}\n\n"
                f"Message:\n{contact_msg.message}"
            )

            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, ['teetobin31@gmail.com'], fail_silently=True,)        # email to be changed 
            except Exception as e:
                pass
            messages.success(request, "Thank you! Your message has been received. We'll get back to you shortly.")
            return redirect('adverse:contact')
        else:
            messages.error(request, "There was an error with your submission. Please check the fields below.")
    else:
        form = ContactForm()

    return render(request, 'adverse/contact.html', {'form': form})
    