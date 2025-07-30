# apps/users/middleware.py

from django.shortcuts import redirect

class RequirePhoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated and
            not request.user.phone and
            not request.path.startswith('/phone') and
            not request.path.startswith('/admin')
        ):
            return redirect('/phone/')
        return self.get_response(request)
