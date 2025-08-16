from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # 이미 로그인된 유저라면 바로 redirect
        if request.user.is_authenticated:
            return redirect('/')
    
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        # 소셜 로그인 유저라면 provider, uid 설정
        if sociallogin.account:
            user.provider = sociallogin.account.provider  # "google", "kakao", "naver"
            user.provider_uid = sociallogin.account.uid
            user.save()

        return user