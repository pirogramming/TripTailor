from django.conf import settings

def fontawesome_key(request):
    return {"FONT_AWESOME_KEY": settings.FONT_AWESOME_KEY}