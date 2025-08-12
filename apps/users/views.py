from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


def login_page(request):
    # 이미 로그인 상태면 마이페이지로
    if request.user.is_authenticated:
        return redirect("users:main_page")
    return render(request, "accounts/login.html")


@login_required(login_url="/accounts/login/")
def main_page(request):
    return render(request, "users/mypage.html")