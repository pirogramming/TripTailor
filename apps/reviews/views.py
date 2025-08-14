from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .models import Review, ReviewPhoto
from apps.places.models import Place

class PlaceReviewCreateView(LoginRequiredMixin, CreateView):
    model = Review
    template_name = 'reviews/place_review_form.html'
    fields = ['title', 'rating', 'content', 'summary']

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.place_id = self.kwargs.get('place_id')
        
        # 루트 선택 처리 (필수)
        route_id = self.request.POST.get('route')
        if not route_id:
            form.add_error('route', '루트를 선택해주세요.')
            return self.form_invalid(form)
        
        from apps.routes.models import Route
        try:
            route = Route.objects.get(id=route_id, creator=self.request.user)
            form.instance.route = route
        except Route.DoesNotExist:
            form.add_error('route', '유효하지 않은 루트입니다.')
            return self.form_invalid(form)
        
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
        
        # 사용자의 루트 목록 추가
        from apps.routes.models import Route
        context['user_routes'] = Route.objects.filter(creator=self.request.user).order_by('-created_at')
        
        return context

class PlaceReviewUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Review
    template_name = 'reviews/place_review_form.html'
    fields = ['title', 'rating', 'content', 'summary']

    def test_func(self):
        review = self.get_object()
        return review.user == self.request.user

    def form_valid(self, form):
        # 루트 선택 처리 (필수)
        route_id = self.request.POST.get('route')
        if not route_id:
            form.add_error('route', '루트를 선택해주세요.')
            return self.form_invalid(form)
        
        from apps.routes.models import Route
        try:
            route = Route.objects.get(id=route_id, creator=self.request.user)
            form.instance.route = route
        except Route.DoesNotExist:
            form.add_error('route', '유효하지 않은 루트입니다.')
            return self.form_invalid(form)
        
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
        
        # 사용자의 루트 목록 추가
        from apps.routes.models import Route
        context['user_routes'] = Route.objects.filter(creator=self.request.user).order_by('-created_at')
        
        # 현재 선택된 루트와 이미지 URL 추가
        if self.object.route:
            context['selected_route_id'] = self.object.route.id
        
        # 현재 이미지들을 배열로 전달
        context['current_photo_urls'] = [photo.url for photo in self.object.photos.all()]
        
        return context

# HTMX를 위한 댓글 목록 뷰
def place_review_list_htmx(request, place_id):
    """HTMX로 댓글 목록을 반환하는 뷰"""
    print(f"DEBUG: place_review_list_htmx 호출됨, place_id: {place_id}")
    
    place = get_object_or_404(Place, pk=place_id)
    print(f"DEBUG: Place 찾음: {place.name}")
    
    reviews = Review.objects.filter(place=place).select_related('user', 'route').order_by('-created_at')
    print(f"DEBUG: 댓글 개수: {reviews.count()}")
    
    for review in reviews:
        print(f"DEBUG: 댓글 - {review.title} by {review.user.username}, 루트: {review.route.title if review.route else 'None'}")
    
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