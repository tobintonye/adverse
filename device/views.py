from django.shortcuts import render, redirect, get_object_or_404


from django.contrib.auth import get_user_model


User = get_user_model()


def RegisterDevice(request):
    return render(request, "Hello")