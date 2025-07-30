from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User

def login_page(request):
    return render(request, 'users/login.html')

@login_required
def enter_phone(request):
    if request.user.phone:
        return redirect('/') #홈으로 가기. 수정 필요

    if request.method == 'POST':
        phone = request.POST.get('phone')

        # 중복 체크
        if User.objects.filter(phone=phone).exclude(pk=request.user.pk).exists():
            messages.error(request, '이미 등록된 전화번호입니다.')
            return render(request, 'users/enter_phone.html')

        request.user.phone = phone
        request.user.save()
        return redirect('/') #홈으로 가기. 수정 필요

    return render(request, 'users/enter_phone.html')