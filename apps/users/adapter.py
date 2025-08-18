# apps/users/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.text import slugify
import uuid

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    # (네가 이미 가진 pre_social_login 유지)

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        이메일이 있을 때만 자동가입 허용.
        카카오는 kakao_account.email에 들어옴.
        """
        extra = sociallogin.account.extra_data or {}
        email = (
            extra.get("email")
            or extra.get("kakao_account", {}).get("email")
        )
        return bool(email)

    def populate_user(self, request, sociallogin, data):
        """
        필수 필드 채워 자동가입 가능 상태로 만듦.
        """
        user = super().populate_user(request, sociallogin, data)
        extra = sociallogin.account.extra_data or {}
        kakao_account = extra.get("kakao_account", {})
        profile = kakao_account.get("profile", {}) or extra.get("properties", {})

        # 이메일 채우기 (필수)
        email = data.get("email") or kakao_account.get("email")
        if email and not getattr(user, "email", None):
            user.email = email

        # username이 필요하면 자동 생성
        if getattr(user, "username", None) in (None, ""):
            base = (
                data.get("username")
                or data.get("name")
                or profile.get("nickname")
                or (email.split("@")[0] if email else "")
            )
            user.username = slugify(base) or f"user_{uuid.uuid4().hex[:10]}"

        return user

    def save_user(self, request, sociallogin, form=None):
        """
        사용자 저장(네 기존 provider/uid 저장 로직 포함 가능)
        """
        user = super().save_user(request, sociallogin, form)
        # 예: user.provider/user.provider_uid 필드가 있으면 채우기
        if hasattr(user, "provider"):
            user.provider = sociallogin.account.provider
        if hasattr(user, "provider_uid"):
            user.provider_uid = sociallogin.account.uid
        user.save()
        return user
