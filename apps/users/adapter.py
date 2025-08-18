from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect
from allauth.account.utils import user_username
from django.utils.text import slugify

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # 이미 로그인된 유저라면 바로 redirect
        if request.user.is_authenticated:
            return redirect('/')
    
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        nickname = sociallogin.account.extra_data.get("name", "")
        if nickname:
            user_username(user, slugify(nickname))

        # 소셜 로그인 유저라면 provider, uid 설정
        if sociallogin.account:
            user.provider = sociallogin.account.provider  # "google", "kakao", "naver"
            user.provider_uid = sociallogin.account.uid
            
        user.save()
        return user