# apps/reviews/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Review, ReviewPhoto

class ReviewForm(forms.ModelForm):
    # 평점 선택 옵션 정의
    RATING_CHOICES = [
        ('', '평점 선택'),
        ('5.0', '5.0'),
        ('4.5', '4.5'),
        ('4.0', '4.0'),
        ('3.5', '3.5'),
        ('3.0', '3.0'),
        ('2.5', '2.5'),
        ('2.0', '2.0'),
        ('1.5', '1.5'),
        ('1.0', '1.0'),
        ('0.5', '0.5'),
        ('0.0', '0.0'),
    ]
    
    rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Review
        fields = ['rating', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 6, 'placeholder': '리뷰 내용을 작성하세요.', 'required': True}),
        }

    def clean_rating(self):
        # 폼 단에서도 0.0~5.0 범위 체크(모델 validator와 중복이지만 UX 향상)
        from decimal import Decimal
        
        rating = self.cleaned_data.get('rating')
        if not rating:
            return None
        
        try:
            rating_decimal = Decimal(str(rating))
            if rating_decimal < Decimal('0.0') or rating_decimal > Decimal('5.0'):
                raise forms.ValidationError("평점은 0.0 이상 5.0 이하여야 합니다.")
            return rating_decimal
        except (ValueError, TypeError):
            raise forms.ValidationError("올바른 평점을 선택해주세요.") 

# 파일 업로드용 폼셋 (더 이상 URL 기반이 아님)
ReviewPhotoFormSet = inlineformset_factory(
    Review,
    ReviewPhoto,
    fields=['image'],
    extra=3,           # 기본 3칸 노출
    can_delete=True,
    max_num=5,         # 최대 5장
    validate_max=True,
    widgets={
        'image': forms.ClearableFileInput(attrs={
            'accept': 'image/*',
            'class': 'form-control'
        })
    }
)