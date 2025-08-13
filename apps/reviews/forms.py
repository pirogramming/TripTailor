# apps/reviews/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Review, ReviewPhoto

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['title', 'route', 'rating', 'summary', 'content']
        widgets = {
            'route': forms.Select(attrs={'required': True, 'placeholder': '여행 경로를 선택하세요'}),
            'title': forms.TextInput(attrs={'placeholder': '게시물 제목을 입력하세요', 'required': True}),
            'rating': forms.NumberInput(attrs={
                'step': '0.1', 
                'min': '0.0', 
                'max': '5.0',
                'placeholder': '0.0 ~ 5.0',
                'required': True
            }),
            'summary': forms.TextInput(attrs={'placeholder': '한 줄 요약(최대 255자)', 'required': True}),
            'content': forms.Textarea(attrs={'rows': 6, 'placeholder': '리뷰 내용을 작성하세요.', 'required': True}),
        }

    def clean_rating(self):
        # 폼 단에서도 0.0~5.0 범위 체크(모델 validator와 중복이지만 UX 향상)
        rating = self.cleaned_data.get('rating')
        if rating is None:
            return 5.0  # 기본값 반환
        
        try:
            rating_float = float(rating)
            if rating_float < 0.0 or rating_float > 5.0:
                raise forms.ValidationError("평점은 0.0 이상 5.0 이하여야 합니다.")
            # 소수점 첫째 자리로 반올림
            return round(rating_float, 1)
        except (ValueError, TypeError):
            return 5.0  # 기본값 반환

    def clean_route(self):
        # Route는 필수 입력 항목
        route = self.cleaned_data.get('route')
        if not route:
            raise forms.ValidationError("여행 경로를 선택해주세요.")
        return route

ReviewPhotoFormSet = inlineformset_factory(
    Review,
    ReviewPhoto,
    fields=['url'],
    extra=3,           # 기본 3칸 노출
    can_delete=True,
    max_num=5,         # 최대 5장
    validate_max=True,
    widgets={
        'url': forms.URLInput(attrs={
            'placeholder': '사진 URL (선택사항)',
            'required': False
        })
    }
)
