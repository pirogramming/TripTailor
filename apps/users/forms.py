# apps/users/forms.py
from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

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
