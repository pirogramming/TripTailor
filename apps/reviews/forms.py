# apps/reviews/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Review, ReviewPhoto

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'content']
        widgets = {
            'rating': forms.NumberInput(attrs={
                'step': '0.5', 
                'min': '0.0', 
                'max': '5.0',
                'placeholder': '0.0 ~ 5.0',
                'required': True
            }),
            'content': forms.Textarea(attrs={'rows': 6, 'placeholder': '리뷰 내용을 작성하세요.', 'required': True}),
        }

    def clean_rating(self):
        # 폼 단에서도 0.0~5.0 범위 체크(모델 validator와 중복이지만 UX 향상)
        rating = self.cleaned_data.get('rating')
        if rating is None:
            return None
        
        try:
            rating_float = float(rating)
            if rating_float < 0.0 or rating_float > 5.0:
                raise forms.ValidationError("평점은 0.0 이상 5.0 이하여야 합니다.")
            return round(rating_float, 1)
        except (ValueError, TypeError):
            return None 

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