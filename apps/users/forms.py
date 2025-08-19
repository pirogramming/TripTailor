# apps/users/forms.py
from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from allauth.account.forms import SignupForm
from django.utils.text import slugify

User = get_user_model()

class CustomPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        """비밀번호 재설정 링크를 받을 수 있는 유저만 리턴"""
        active_users = User._default_manager.filter(email__iexact=email, is_active=True)
        # local 로그인 유저만 필터링
        return [user for user in active_users if user.has_usable_password() and user.provider == "local"]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        users = list(self.get_users(email))

        if not users:
            # 로컬 유저가 아니라면 일단 ValidationError로 처리
            raise forms.ValidationError(_("비밀번호 재설정을 할 수 있는 계정이 아닙니다."))

        return email

class EmailSignupForm(SignupForm):
    """
    일반 회원가입 화면에서 보여줄 폼.
    기본적으로 email, password1, password2는 SignupForm에 포함되어 있음.
    username을 받고 싶으면 required를 켜주면 됨.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 닉네임/아이디 받고 싶으면 True, 아니라면 False로 두면 숨김
        if "username" in self.fields:
            self.fields["username"].required = True
            self.fields["username"].label = "닉네임"
            self.fields["username"].help_text = ""

    def save(self, request):
        user = super().save(request)
        # 로컬 가입 표시(비번 재설정 허용 기준과 일치)
        if hasattr(user, "provider") and not user.provider:
            user.provider = "local"
        # username unique 보호(필요 시 슬러그 처리)
        if hasattr(user, "username") and user.username:
            user.username = slugify(user.username) or user.username
        user.save()
        return user
