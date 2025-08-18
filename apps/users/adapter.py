from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect
from allauth.account.utils import user_username
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from allauth.exceptions import ImmediateHttpResponse
from django.contrib import messages

User = get_user_model()

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # 이미 로그인된 유저라면 그냥 redirect
        if request.user.is_authenticated:
            return redirect('/')

        # 이메일 중복 여부 확인
        email = sociallogin.account.extra_data.get("email")
        if email and User.objects.filter(email=email).exists():
            # 메시지 띄우고 로그인 중단 (redirect 처리)
            messages.error(request, "이미 해당 이메일로 가입된 계정이 있습니다. 소셜 로그인할 수 없습니다.")
            raise ImmediateHttpResponse(redirect("/accounts/login/"))  # 원하는 경로로 변경 가능

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        # 소셜 닉네임을 username으로 설정
        nickname = sociallogin.account.extra_data.get("name", "")
        if nickname:
            user.username = slugify(nickname)

        # 소셜 계정 정보 저장
        if sociallogin.account:
            user.provider = sociallogin.account.provider
            user.provider_uid = sociallogin.account.uid

        user.save()
        return user
