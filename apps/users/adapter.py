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
        if request.user.is_authenticated:
            return redirect('/')

        email = sociallogin.account.extra_data.get("email")
        if email:
            try:
                existing_user = User.objects.get(email=email)

                # ✅ 해당 이메일이 '소셜 유저'가 아닌 경우만 로그인 막기
                if not hasattr(existing_user, "socialaccount"):
                    messages.error(request, "이미 해당 이메일로 가입된 계정이 있습니다. 소셜 로그인할 수 없습니다.")
                    raise ImmediateHttpResponse(redirect("/accounts/login/"))

            except User.DoesNotExist:
                pass  # 존재하지 않으면 그냥 자동가입 진행

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        nickname = sociallogin.account.extra_data.get("name", "")
        if nickname:
            user.username = slugify(nickname)

        if sociallogin.account:
            user.provider = sociallogin.account.provider
            user.provider_uid = sociallogin.account.uid

        user.save()
        return user
