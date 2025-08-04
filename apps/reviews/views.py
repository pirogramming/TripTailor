from django.shortcuts import render

# Create your views here.
# apps/reviews/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from .forms import ReviewForm, ReviewPhotoFormSet
from .models import Review



class ReviewListView(ListView):
    model = Review
    template_name = 'reviews/review_list.html'
    context_object_name = 'reviews'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('user', 'route').prefetch_related('photos')
        route_id = self.request.GET.get('route')
        user_id = self.request.GET.get('user')
        if route_id:
            qs = qs.filter(route_id=route_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
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

    def get_contextData(self, **kwargs):  # 오타 방지: 아래에서 정확히 get_context_data로 작성
        return super().get_context_data(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        else:
            context['photo_formset'] = ReviewPhotoFormSet()
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        formset = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            messages.success(self.request, "리뷰가 등록되었습니다.")
            return response
        else:
            # 폼셋 오류 시 다시 폼 렌더
            return self.form_invalid(form)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        return self.render_to_response(context)

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
            context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        else:
            context['photo_formset'] = ReviewPhotoFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        formset = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        if formset.is_valid():
            formset.save()
            messages.success(self.request, "리뷰가 수정되었습니다.")
            return response
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        context['photo_formset'] = ReviewPhotoFormSet(self.request.POST, instance=self.object)
        return self.render_to_response(context)

class ReviewDeleteView(LoginRequiredMixin, AuthorRequiredMixin, DeleteView):
    model = Review
    template_name = 'reviews/review_confirm_delete.html'
    success_url = reverse_lazy('reviews:list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "리뷰가 삭제되었습니다.")
        return super().delete(request, *args, **kwargs)
