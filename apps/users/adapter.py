from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # 이미 로그인된 유저라면 바로 redirect
        if request.user.is_authenticated:
            return redirect('/')
