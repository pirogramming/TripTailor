# apps/reviews/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Review, ReviewPhoto

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['route', 'rating', 'summary', 'content']
        widgets = {
            'summary': forms.TextInput(attrs={'placeholder': '한 줄 요약(최대 255자)'}),
            'content': forms.Textarea(attrs={'rows': 6, 'placeholder': '리뷰 내용을 작성하세요.'}),
        }

    def clean_rating(self):
        # 폼 단에서도 0.0~5.0 범위 체크(모델 validator와 중복이지만 UX 향상)
        rating = self.cleaned_data['rating']
        if rating is None:
            raise forms.ValidationError("평점을 입력하세요.")
        if rating < 0 or rating > 5:
            raise forms.ValidationError("평점은 0.0 이상 5.0 이하여야 합니다.")
        # 소수점 첫째 자리 제한 안내(폼 입력 시 반올림)
        return round(float(rating), 1)

ReviewPhotoFormSet = inlineformset_factory(
    Review,
    ReviewPhoto,
    fields=['url'],
    extra=3,           # 기본 3칸 노출
    can_delete=True,
    max_num=5,         # 최대 5장
    validate_max=True
)
