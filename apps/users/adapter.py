# apps/users/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.text import slugify
import uuid

User = get_user_model()

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        - 로그인된 상태면 통과
        - 동일 이메일의 기존 유저가 있는데 현재 provider가 아니면 차단(중복 가입 방지)
        """
        if request.user.is_authenticated:
            return

        extra = sociallogin.account.extra_data or {}
        email = extra.get("email") or extra.get("kakao_account", {}).get("email")
        provider = sociallogin.account.provider  # "kakao" / "google" / "naver" ...

        if not email:
            # 이메일 없이 들어오면 폼으로 가지 않게 즉시 리다이렉트
            messages.error(request, "카카오 이메일 제공에 동의해야 로그인할 수 있어요.")
            raise ImmediateHttpResponse(redirect("/accounts/login/"))

        try:
            existing = User.objects.get(email__iexact=email)
            # 같은 이메일의 유저가 있는데, 해당 provider로 연결되지 않았다면 막기
            if not SocialAccount.objects.filter(user=existing, provider=provider).exists():
                messages.error(request, "이미 해당 이메일로 가입된 계정이 있어 소셜 로그인할 수 없습니다.")
                raise ImmediateHttpResponse(redirect("/accounts/login/"))
        except User.DoesNotExist:
            pass  # 없으면 계속 진행

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        이메일이 있을 때만 추가 폼 없이 자동가입 허용.
        (없으면 pre_social_login에서 이미 차단됨)
        """
        extra = sociallogin.account.extra_data or {}
        email = extra.get("email") or extra.get("kakao_account", {}).get("email")
        return bool(email)

    def populate_user(self, request, sociallogin, data):
        """
        소셜 데이터로 User 필수 필드 채우기 (email/username).
        """
        user = super().populate_user(request, sociallogin, data)

        extra = sociallogin.account.extra_data or {}
        kakao_account = extra.get("kakao_account", {})
        profile = kakao_account.get("profile", {}) or extra.get("properties", {})

        # 이메일 채우기 (필수)
        email = data.get("email") or kakao_account.get("email")
        if email and not getattr(user, "email", None):
            user.email = email

        # username 자동 생성 (없으면 닉네임/이메일 앞부분/랜덤)
        if not getattr(user, "username", None):
            base = (
                data.get("username")
                or data.get("name")
                or (profile.get("nickname") if isinstance(profile, dict) else None)
                or (email.split("@")[0] if email else "")
            )
            user.username = slugify(base or f"user-{uuid.uuid4().hex[:10]}")
        return user

    def save_user(self, request, sociallogin, form=None):
        """
        저장 시 provider / provider_uid도 기록(있을 때만).
        """
        user = super().save_user(request, sociallogin, form)
        if hasattr(user, "provider"):
            user.provider = sociallogin.account.provider
        if hasattr(user, "provider_uid"):
            user.provider_uid = sociallogin.account.uid
        user.save()
        return user