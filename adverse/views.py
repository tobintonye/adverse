from django.shortcuts import render, redirect
from django.contrib import messages
from adverseproject.emails import send_adverse_email
from .forms import ContactForm


def home(request):
    return render(request, 'adverse/home.html')

def about(request):
    return render(request, 'adverse/about.html')

def how_it_works(request):
    return render(request, 'adverse/how_it_works.html')

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_msg = form.save()

            context = {
                "contact_name": contact_msg.name,
                "contact_email": contact_msg.email,
                "contact_role": contact_msg.role,
                "contact_message": contact_msg.message,
            }

            send_adverse_email(
                template="contact_message",
                to="teetobin31@gmail.com", # to be changed
                context=context,
                subject_prefix=f"[AdVers Contact - {contact_msg.role}]"
            )

            if request.headers.get('HX-Request'):
                return render(request, 'adverse/partials/contact_success.html')
            
            messages.success(request, "Thank you! Your message has been received. We'll get back to you shortly.")
            return redirect('adverse:contact')
        else:
            messages.error(request, "There was an error with your submission. Please check the fields below.")

            if request.headers.get('HX-Request'):
                return render(request, 'adverse/contact.html', {'form': form})
            
            return redirect('adverse:contact')
    else:
        form = ContactForm()
        
    return render(request, 'adverse/contact.html', {'form': form})