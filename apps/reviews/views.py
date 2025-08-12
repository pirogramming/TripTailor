from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .forms import ReviewForm, ReviewPhotoFormSet
from .models import Review

# ✅ services 폴더 없이, management command에 정의된 클래스를 재사용 (fallback 포함)
try:
    from apps.reviews.management.commands.review_compare import ReviewPipelineService
except Exception:
    try:
        from reviews.management.commands.review_compare import ReviewPipelineService
    except Exception:
        ReviewPipelineService = None  # import 실패해도 뷰 동작은 유지


class ReviewListView(ListView):
    model = Review
    template_name = 'reviews/review_list.html'
    context_object_name = 'reviews'
    paginate_by = 10

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related('user', 'route')
            .prefetch_related('photos')
            .order_by('-id')
        )

        route_id = self.request.GET.get('route')
        if route_id:
            qs = qs.filter(route_id=route_id)

        # 안전한 사용자 필터:
        # - mine=1 이면 로그인 유저 본인 것만
        # - user=<id> 는 staff 에게만 허용
        mine = self.request.GET.get('mine')
        user_param = self.request.GET.get('user')
        if mine in ('1', 'true', 'True'):
            if not self.request.user.is_authenticated:
                raise PermissionDenied("로그인이 필요합니다.")
            qs = qs.filter(user_id=self.request.user.id)
        elif user_param and self.request.user.is_staff:
            qs = qs.filter(user_id=user_param)

        return qs


class ReviewDetailView(DetailView):
    model = Review
    template_name = 'reviews/review_detail.html'
    context_object_name = 'review'


class ReviewCreateView(LoginRequiredMixin, CreateView):
    model = Review
    form_class = ReviewForm
    template_name = 'reviews/review_form.html'

    def get_initial(self):
        initial = super().get_initial()
        route_id = self.request.GET.get('route')
        if route_id:
            initial['route'] = route_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, self.request.FILES)
        else:
            context['photo_formset'] = ReviewPhotoFormSet()
        return context

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, self.request.FILES)
        return self.render_to_response(context)

    def form_valid(self, form):
        try:
            review = form.save(commit=False)
            review.user = self.request.user

            # 안전한 기본값 보정
            title = form.cleaned_data.get('title') or '리뷰'
            summary = form.cleaned_data.get('summary') or '리뷰'
            content = form.cleaned_data.get('content') or ''
            review.title = title
            review.summary = summary
            review.content = content

            # 평점 보정 (소수점 1자리, 0~5 사이)
            rating = form.cleaned_data.get('rating')
            try:
                if rating is None:
                    rating = Decimal('5.0')
                rating = Decimal(rating).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                if rating < Decimal('0.0'):
                    rating = Decimal('0.0')
                if rating > Decimal('5.0'):
                    rating = Decimal('5.0')
            except (InvalidOperation, ValueError, TypeError):
                rating = Decimal('5.0')
            review.rating = rating

            review.save()

            formset = ReviewPhotoFormSet(self.request.POST, self.request.FILES, instance=review)
            if formset.is_valid():
                formset.save()
                messages.success(self.request, "리뷰가 등록되었습니다.")
            else:
                messages.warning(self.request, "리뷰는 저장되었지만 사진 처리에 문제가 있었습니다.")

            # ✅ 파이프라인 실행: 커밋 완료 후
            if ReviewPipelineService:
                try:
                    transaction.on_commit(lambda: ReviewPipelineService().process_review(review))
                    messages.info(self.request, "AI 파이프라인 실행을 예약했습니다.")
                except Exception as e:
                    messages.warning(self.request, f"AI 파이프라인 예약 중 오류가 발생했습니다: {e}")
            else:
                messages.info(self.request, "AI 파이프라인 모듈을 찾지 못해 실행을 건너뜁니다.")

            return redirect('reviews:list')

        except Exception as e:
            messages.error(self.request, f"리뷰 저장 중 오류가 발생했습니다: {e}")
            return self.form_invalid(form)


class AuthorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        obj = self.get_object()
        return obj.user_id == self.request.user.id


class ReviewUpdateView(LoginRequiredMixin, AuthorRequiredMixin, UpdateView):
    model = Review
    form_class = ReviewForm
    template_name = 'reviews/review_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, self.request.FILES, instance=self.object)
        else:
            context['photo_formset'] = ReviewPhotoFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        try:
            # cleaned_data 기반으로 안전하게 반영
            cd = form.cleaned_data
            self.object.title = cd.get('title') or '리뷰'
            self.object.route = cd.get('route')  # None 허용
            self.object.summary = cd.get('summary') or '리뷰'
            self.object.content = cd.get('content') or ''

            rating = cd.get('rating')
            try:
                if rating is None:
                    rating = Decimal('5.0')
                rating = Decimal(rating).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                if rating < Decimal('0.0'):
                    rating = Decimal('0.0')
                if rating > Decimal('5.0'):
                    rating = Decimal('5.0')
            except (InvalidOperation, ValueError, TypeError):
                rating = Decimal('5.0')
            self.object.rating = rating

            self.object.save()

            formset = ReviewPhotoFormSet(self.request.POST, self.request.FILES, instance=self.object)
            if formset.is_valid():
                formset.save()
                messages.success(self.request, "리뷰가 수정되었습니다.")
            else:
                messages.warning(self.request, "리뷰는 수정되었지만 사진 처리에 문제가 있었습니다.")

            # ✅ 파이프라인 실행: 커밋 완료 후
            if ReviewPipelineService:
                try:
                    transaction.on_commit(lambda: ReviewPipelineService().process_review(self.object))
                    messages.info(self.request, "AI 파이프라인 실행을 예약했습니다.")
                except Exception as e:
                    messages.warning(self.request, f"AI 파이프라인 예약 중 오류가 발생했습니다: {e}")
            else:
                messages.info(self.request, "AI 파이프라인 모듈을 찾지 못해 실행을 건너뜁니다.")

            return redirect('reviews:list')

        except Exception as e:
            messages.error(self.request, f"리뷰 수정 중 오류가 발생했습니다: {e}")
            return self.form_invalid(form)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, self.request.FILES, instance=self.object)
        return self.render_to_response(context)


class ReviewDeleteView(LoginRequiredMixin, AuthorRequiredMixin, DeleteView):
    model = Review
    template_name = 'reviews/review_delete.html'
    success_url = reverse_lazy('reviews:list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "리뷰가 삭제되었습니다.")
        return super().delete(request, *args, **kwargs)
