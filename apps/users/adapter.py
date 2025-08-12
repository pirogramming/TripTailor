from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.shortcuts import redirect


class MyAccountAdapter(DefaultAccountAdapter):
    """Ensure we always redirect to LOGIN_REDIRECT_URL after local login."""
    def get_login_redirect_url(self, request):
        return getattr(settings, "LOGIN_REDIRECT_URL", "/")


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    """If a logged-in user hits a social login, just send them home."""
    def pre_social_login(self, request, sociallogin):
        if request.user.is_authenticated:
            return redirect(getattr(settings, "LOGIN_REDIRECT_URL", "/"))