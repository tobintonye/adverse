from django.shortcuts import render
# Create your views here.
def home(request):
    return render (request, 'adverse/home.html')

def about(request):
    return render(request, 'adverse/about.html')

def how_it_works(request):
    return render(request, 'adverse/how_it_works.html')

def contact(request):
    return render(request, 'adverse/contact.html')