from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

import re
import requests
from django.http import JsonResponse, Http404
from django.conf import settings
from urllib.parse import quote
from apps.places.models import Place

from .forms import ReviewForm, ReviewPhotoFormSet
from .models import Review

# ✅ services 폴더 없이, management command에 정의된 클래스를 재사용
from apps.reviews.management.commands.review_compare import ReviewPipelineService

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

class ReviewListView(LoginRequiredMixin, ListView):
    model = Review
    template_name = 'reviews/review_list.html'
    context_object_name = 'reviews'
    paginate_by = 10
    login_url = '/login/'  # 로그인 페이지 URL
    # 로그인이 필요한 상태로 변경

    def get_queryset(self):
        qs = super().get_queryset().select_related('user', 'route').prefetch_related('photos')
        route_id = self.request.GET.get('route')
        user_id = self.request.GET.get('user')
        if route_id:
            qs = qs.filter(route_id=route_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs


class ReviewDetailView(LoginRequiredMixin, DetailView):
    model = Review
    template_name = 'reviews/review_detail.html'
    context_object_name = 'review'
    login_url = '/login/'  # 로그인 페이지 URL
    # 로그인이 필요한 상태로 변경


class ReviewCreateView(LoginRequiredMixin, CreateView):
    model = Review
    form_class = ReviewForm
    template_name = 'reviews/review_form.html'
    login_url = '/login/'  # 로그인 페이지 URL

    def get_initial(self):
        initial = super().get_initial()
        route_id = self.request.GET.get('route')
        if route_id:
            initial['route'] = route_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        else:
            context['photo_formset'] = ReviewPhotoFormSet()
        return context

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        if hasattr(self, 'object') and self.object:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        else:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST)
        return self.render_to_response(context)

    def form_valid(self, form):
        try:
            title = form.cleaned_data.get('title', '리뷰')
            route = form.cleaned_data.get('route')  # None 가능
            rating = form.cleaned_data.get('rating', 5.0)
            summary = form.cleaned_data.get('summary', '리뷰')
            content = form.cleaned_data.get('content', '')

            review = form.save(commit=False)
            review.user = self.request.user
            review.title = title
            review.route = route
            review.rating = rating
            review.summary = summary
            review.content = content
            review.save()

            formset = ReviewPhotoFormSet(self.request.POST, instance=review)
            if formset.is_valid():
                formset.save()
                messages.success(self.request, "리뷰가 등록되었습니다.")
            else:
                messages.warning(self.request, "리뷰는 저장되었지만 사진 처리에 문제가 있었습니다.")

            # ✅ 파이프라인 실행
            try:
                pipeline_service = ReviewPipelineService()
                pipeline_success = pipeline_service.process_review(review)
                if pipeline_success:
                    messages.info(self.request, "AI 파이프라인이 성공적으로 실행되었습니다.")
                else:
                    messages.info(self.request, "AI 파이프라인이 실행되었지만 업데이트가 필요하지 않았습니다.")
            except Exception as e:
                messages.warning(self.request, f"AI 파이프라인 실행 중 오류가 발생했습니다: {str(e)}")

            return redirect('reviews:list')

        except Exception as e:
            messages.error(self.request, f"리뷰 저장 중 오류가 발생했습니다: {str(e)}")
            return self.form_invalid(form)


class AuthorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        obj = self.get_object()
        return obj.user_id == self.request.user.id


class ReviewUpdateView(LoginRequiredMixin, AuthorRequiredMixin, UpdateView):
    model = Review
    form_class = ReviewForm
    template_name = 'reviews/review_form.html'
    login_url = '/login/'  # 로그인 페이지 URL

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        else:
            context['photo_formset'] = ReviewPhotoFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        try:
            title = form.data.get('title', '리뷰')
            route_id = form.data.get('route')
            rating = form.data.get('rating')
            summary = form.data.get('summary')
            content = form.data.get('content')

            self.object.title = title
            self.object.route_id = route_id or None

            if rating:
                try:
                    rating_float = float(rating)
                    rating_rounded = round(rating_float, 1)
                except ValueError:
                    rating_rounded = 5.0
            else:
                rating_rounded = 5.0

            self.object.rating = rating_rounded
            self.object.summary = summary or "리뷰"
            self.object.content = content or ""
            self.object.save()

            formset = ReviewPhotoFormSet(self.request.POST, instance=self.object)
            if formset.is_valid():
                formset.save()
                messages.success(self.request, "리뷰가 수정되었습니다.")
            else:
                messages.warning(self.request, "리뷰는 수정되었지만 사진 처리에 문제가 있었습니다.")

            # ✅ 파이프라인 실행
            try:
                pipeline_service = ReviewPipelineService()
                pipeline_success = pipeline_service.process_review(self.object)
                if pipeline_success:
                    messages.info(self.request, "AI 파이프라인이 성공적으로 실행되었습니다.")
                else:
                    messages.info(self.request, "AI 파이프라인이 실행되었지만 업데이트가 필요하지 않았습니다.")
            except Exception as e:
                messages.warning(self.request, f"AI 파이프라인 실행 중 오류가 발생했습니다: {str(e)}")

            return redirect('reviews:list')

        except Exception as e:
            messages.error(self.request, f"리뷰 수정 중 오류가 발생했습니다: {str(e)}")
            return self.form_invalid(form)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        return self.render_to_response(context)


class ReviewDeleteView(LoginRequiredMixin, AuthorRequiredMixin, DeleteView):
    model = Review
    template_name = 'reviews/review_delete.html'
    success_url = reverse_lazy('reviews:list')
    login_url = '/login/'  # 로그인 페이지 URL

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "리뷰가 삭제되었습니다.")
        return super().delete(request, *args, **kwargs)

