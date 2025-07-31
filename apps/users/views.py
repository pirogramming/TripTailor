from django.shortcuts import render

def login_page(request):
    return render(request, 'users/login.html')

def home(request):
    return render(request, 'users/home.html', {
        'username': request.user.username
    })