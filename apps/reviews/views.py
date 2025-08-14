from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

import re
import requests
from django.http import JsonResponse, Http404
from django.conf import settings


from .models import Review, ReviewPhoto
from apps.places.models import Place

BLACKLIST_SUBSTR = (
    "smartstore.naver.com", "shopping.naver.com", "brand.naver.com",
    "/product/", "/category/", "/ads", "/event", "news.naver.com"
)


def _is_allowed_link(link: str) -> bool:
    url = (link or "").lower()
    if any(b in url for b in BLACKLIST_SUBSTR):
        return False
    # 대표 블로그 도메인들 (넓게 허용)
    return any(d in url for d in (
        "blog.naver.com", "m.blog.naver.com",
        "post.naver.com", "naver.me",
        "tistory.com", "brunch.co.kr", "velog.io"
    ))

def _loose_contains(text: str, place_name: str) -> bool:
    # 괄호/공백/특수문자 제거 후 포함 여부
    def norm(s): return re.sub(r"[\s\(\)\[\]\{\}\-_/·•~!@#$%^&*=+|:;\"'<>?,.]+", "", s or "")
    t = norm(text)
    n = norm(place_name)
    # 이름이 너무 짧으면(2자 이하) 오탐 많으니 패스
    if len(n) <= 2:
        return n in t and len(t) > 10
    # 이름 그대로 또는 괄호 제거 버전 일부라도 포함
    return (n in t) or (n[: max(3, len(n)//2)] in t)

def blog_reviews(request, place_id: int):
    try:
        place = Place.objects.get(id=place_id)
    except Place.DoesNotExist:
        raise Http404("Place not found")

    city = getattr(place, "city", "") or getattr(place, "region", "") or ""
    # 폴백 쿼리 세트 (점점 완화)
    queries = [
        f"\"{place.name}\" {city} 후기",
        f"{place.name} {city} 후기",
        f"{place.name} 후기",
        f"{place.name} 여행기",
        f"{place.name} 방문기",
    ]

    collected = []
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    url = "https://openapi.naver.com/v1/search/blog.json"

    for q in queries:
        params = {"query": q, "display": 30, "start": 1, "sort": "sim"}  # 정확도 우선
        try:
            r = requests.get(url, params=params, headers=headers, timeout=5)
            r.raise_for_status()
            items = r.json().get("items", [])
        except requests.RequestException:
            continue

        for it in items:
            title = it.get("title", "")
            desc = it.get("description", "")
            link = it.get("link", "")

            if not _is_allowed_link(link):
                continue
            if not _loose_contains(title + " " + desc, place.name):
                continue

            collected.append({
                "title": title, "link": link,
                "summary": desc,
                "blogger": it.get("bloggername", ""),
                "postdate": it.get("postdate", ""),
            })

        # 충분히 모이면 종료
        if len(collected) >= 10:
            break

    # 링크 기준 중복 제거
    seen, dedup = set(), []
    for x in collected:
        if x["link"] in seen:
            continue
        seen.add(x["link"])
        dedup.append(x)

    return JsonResponse({"items": dedup[:10]})

class PlaceReviewCreateView(LoginRequiredMixin, CreateView):
    model = Review
    template_name = 'reviews/place_review_form.html'
    fields = ['rating', 'content']

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.place_id = self.kwargs.get('place_id')
        
        # 댓글 저장
        review = form.save()
        
        # 여러 이미지 URL 처리
        photo_urls = self.request.POST.getlist('photo_urls[]')
        for photo_url in photo_urls:
            if photo_url and photo_url.strip():
                ReviewPhoto.objects.create(review=review, url=photo_url.strip())
        
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('places:place_detail', kwargs={'pk': self.kwargs.get('place_id')})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['place'] = get_object_or_404(Place, pk=self.kwargs.get('place_id'))
        return context

class PlaceReviewUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Review
    template_name = 'reviews/place_review_form.html'
    fields = ['rating', 'content']

    def test_func(self):
        review = self.get_object()
        return review.user == self.request.user

    def form_valid(self, form):
        # 댓글 저장
        review = form.save()
        
        # 기존 이미지 삭제 후 새 이미지 URL 처리
        review.photos.all().delete()
        photo_urls = self.request.POST.getlist('photo_urls[]')
        for photo_url in photo_urls:
            if photo_url and photo_url.strip():
                ReviewPhoto.objects.create(review=review, url=photo_url.strip())
        
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('places:place_detail', kwargs={'pk': self.object.place.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['place'] = self.object.place
        
        # 현재 이미지들을 배열로 전달
        context['current_photo_urls'] = [photo.url for photo in self.object.photos.all()]
        
        return context

# HTMX를 위한 댓글 목록 뷰
def place_review_list_htmx(request, place_id):
    """HTMX로 댓글 목록을 반환하는 뷰"""
    print(f"DEBUG: place_review_list_htmx 호출됨, place_id: {place_id}")
    
    place = get_object_or_404(Place, pk=place_id)
    print(f"DEBUG: Place 찾음: {place.name}")
    
    reviews = Review.objects.filter(place=place).select_related('user').order_by('-created_at')
    print(f"DEBUG: 댓글 개수: {reviews.count()}")
    
    for review in reviews:
        print(f"DEBUG: 댓글 - {review.user.username}의 댓글 by {review.user.username}")
    
    return render(request, 'reviews/review_list_fragment.html', {
        'reviews': reviews,
        'place': place,
        'user': request.user
    })

@login_required
def delete_review_ajax(request, place_id, review_id):
    """AJAX로 댓글을 바로 삭제하는 뷰"""
    if request.method == 'POST':
        try:
            review = get_object_or_404(Review, pk=review_id, user=request.user)
            review.delete()
            return JsonResponse({'success': True, 'message': '댓글이 삭제되었습니다.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'삭제 중 오류가 발생했습니다: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'})