from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.

class User(AbstractUser):
    PROVIDER_CHOICES = [
        ("local", "Local (email/phone)"),
        ("google", "Google"),
        ("kakao", "Kakao"),
        ("naver", "Naver"),
        ("apple", "Apple"),
    ]
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="local", blank=True)
    provider_uid = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, unique=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 사용자 조회 성능을 높이기 위한 인덱스 설정
        # provider + provider_uid 조합으로 자주 쿼리할 때 속도 향상
        indexes = [models.Index(fields=["provider", "provider_uid"])]
        
        # 소셜 로그인 사용자에 한해 provider + provider_uid 조합이 유일해야 함
        # 일반 회원가입 (local)은 provider_uid가 null이므로 중복 허용됨
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_uid"],
                condition=models.Q(provider_uid__isnull=False), # provider_uid가 있을 때만 적용
                name="uniq_provider_uid_if_social",
            )
        ]