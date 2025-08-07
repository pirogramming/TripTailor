from django.shortcuts import render

def login_page(request):
    return render(request, 'users/login.html')


def main_page(request):
    return render(request, 'users/mypage.html')