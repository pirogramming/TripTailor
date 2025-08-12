from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, BooleanField, Value, Count, Q
from django.http import JsonResponse

import recommend 
from django.core.paginator import Paginator
from .models import Place, PlaceLike, Tag
import re


def _parse_selected_tags(request):
    raw = (request.GET.get('tags') or '').strip()
    selected = [t for t in raw.split(',') if t]
    match = (request.GET.get('match') or 'any').lower()  # 'any' or 'all'
    return selected, match, raw

# 1) 더 튼튼한 파서
def parse_recommendations(recommendations):
    parsed = []
    name_pat = re.compile(r"\*\*\s*\[?([^\]\*]+?)\]?\s*\*\*")  # **[이름]** 또는 **이름**
    numline_pat = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")         # "1. 장소" 같은 라인 보강

    i = 0
    while i < len(recommendations):
        line = recommendations[i]
        name = None

        m = name_pat.search(line)
        if m:
            name = m.group(1).strip()
        else:
            # 굵게가 없을 때 숫자라인에서 이름 추출
            m2 = numline_pat.match(line)
            if m2:
                name = m2.group(1).strip()
                # 뒤에 ** **가 없는 케이스 보정: 괄호/양끝 기호 제거
                name = re.sub(r"^[\-\*\s\[]+|[\]\s]+$", "", name)

        reason = ""
        if name:
            if i + 1 < len(recommendations):
                nxt = recommendations[i + 1].strip()
                if nxt.startswith("- 이유:") or "이유:" in nxt:
                    reason = nxt.split("이유:", 1)[-1].strip()
                    parsed.append({"name": name, "reason": reason})
                    i += 2
                    continue
            parsed.append({"name": name, "reason": reason})
        i += 1
    return parsed


# 2) DB 매칭을 조금 더 느슨하게 (공백/괄호 제거 후 비교)
def find_places_by_names(names):
    def norm(s):
        import re
        s = s or ""
        s = re.sub(r"[\s\(\)\[\]「」『』\-_/·•~!@#$%^&*=+|:;\"'<>?,.]+", "", s)
        return s.lower()

    # 1차: 넓게 필터링 (QuerySet)
    q = Q()
    for raw in names:
        n = (raw or "").strip()
        if not n:
            continue
        q |= (Q(name__iexact=n) | Q(name__icontains=n) | Q(summary__icontains=n) | Q(address__icontains=n))
    if not q:
        return Place.objects.none()

    candidates = list(Place.objects.filter(q).distinct())

    # 2차: 정규화 유사 매칭으로 추림 → 최종 id 목록 만들기
    idx = {p.id: norm(p.name) for p in candidates}
    pick_ids = []
    for raw in names:
        key_n = norm(raw)
        hit = next((pid for pid, n2 in idx.items() if key_n == n2), None)
        if not hit:
            hit = next((pid for pid, n2 in idx.items() if key_n and key_n in n2), None)
        if hit and hit not in pick_ids:
            pick_ids.append(hit)

    # ✅ 항상 QuerySet 반환
    return Place.objects.filter(id__in=pick_ids)



def with_like_meta(qs, user):
    """
    Place queryset에 like_count / is_liked 를 붙여준다.
    PlaceLike.place 의 related_name 은 'placelikes' 라는 전제.
    """
    qs = qs.annotate(like_count=Count('placelikes', distinct=True))
    if user.is_authenticated:
        qs = qs.annotate(
            is_liked=Exists(
                PlaceLike.objects.filter(place=OuterRef('pk'), user=user)
            )
        )
    else:
        qs = qs.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )
    return qs


def build_context_from_cached(prompt, followup, cached, user):
    recommended_places = []
    recommendations = cached.get('recommendations', []) or []
    question = cached.get('question', '') or ''
    show_followup = bool(question)

    parsed_recs = parse_recommendations(recommendations)
    names = [r["name"] for r in parsed_recs if r.get("name")]
    candidates_qs = with_like_meta(find_places_by_names(names), user)
    candidates = list(candidates_qs)  

    name_index = {p.name: p for p in candidates}
    lower_index = [(p.name.lower(), p) for p in candidates]

    for rec in parsed_recs:
        nm = rec["name"]
        place = name_index.get(nm)
        if not place:
            nm_l = nm.lower()
            place = next((p for name_l, p in lower_index if nm_l in name_l), None)
        if place and not any(x["place"].pk == place.pk for x in recommended_places):
            recommended_places.append({"place": place, "reason": rec.get("reason", "")})

    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places,
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
    }

def get_recommendation_context(prompt, followup, user):
    recommended_places, recommendations, question = [], [], ""
    show_followup = False

    if not prompt:
        return {'prompt': prompt, 'followup': followup, 'recommended_places': [], 'recommendations': [], 'question': "", 'show_followup': False}

    user_input = f"{prompt} {followup}" if followup else prompt
    try:
        result = recommend.app.invoke({"user_input": user_input}) or {}
    except Exception:
        result = {}

    question = (result.get("보충_질문") or result.get("question") or "")
    recommendations = result.get("recommendations") or []

    # 1) 파싱으로 이름 가져오기
    parsed_recs = parse_recommendations(recommendations)
    names = [r.get("name","").strip() for r in parsed_recs if r.get("name")]

    # 2) 모델이 함께 돌려주는 '추천_장소명'도 합치기
    model_names = result.get("추천_장소명") or []
    for n in model_names:
        if n and n not in names:
            names.append(n)

    # 3) 이름 -> DB 매칭
    candidates = find_places_by_names(names)
    like_annotated = list(with_like_meta(Place.objects.filter(id__in=[p.id for p in candidates]), user))
    by_id = {p.id: p for p in like_annotated}

    # 추천 순서 보존해서 붙이기
    used = set()
    for nm in names:
        hit = next((p for p in candidates if p.name == nm), None)
        hit = by_id.get(hit.id) if hit else None
        if hit and hit.id not in used:
            reason = next((r["reason"] for r in parsed_recs if r["name"] == nm and r.get("reason")), "")
            recommended_places.append({"place": hit, "reason": reason})
            used.add(hit.id)

    # 4) 3개가 안되면 채우기: 남은 후보들(좋아요 많은 순)로 보충
    if len(recommended_places) < 3:
        remain = [p for p in like_annotated if p.id not in used]
        remain.sort(key=lambda x: getattr(x, "like_count", 0), reverse=True)
        for p in remain:
            recommended_places.append({"place": p, "reason": ""})
            used.add(p.id)
            if len(recommended_places) >= 3:
                break

    show_followup = bool(question)
    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places[:3],  # 최종 3개 보장
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
    }




def main(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    class_filter = request.GET.get('place_class', '')

    # 기본 목록
    qs = Place.objects.all().order_by('-id')

    # 대분류 필터
    if class_filter and class_filter.isdigit():
        qs = qs.filter(place_class=int(class_filter))

    # ✅ 태그 필터 (Place.tags 기준)
    # URL 예: ?tags=레트로,야경&match=any
    selected, match_mode, _ = _parse_selected_tags(request)

    if selected:
        # 1차: 교집합
        qs_all = qs
        for tag in selected:
            qs_all = qs_all.filter(tags__name=tag)
        qs_all = qs_all.distinct()

        if qs_all.exists():
            qs = qs_all
        else:
            # 2차: 합집합
            qs = qs.filter(tags__name__in=selected).distinct()

    qs = qs.prefetch_related('tags') 
    tags_qs = Tag.objects.order_by('name')


    # 좋아요 메타 붙이기
    qs = qs.prefetch_related('tags')
    qs = with_like_meta(qs, request.user)

    # 페이지네이션
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # 모델 호출 1회
    context = get_recommendation_context(prompt, followup, request.user)

    # 세션 저장
    request.session['last_reco'] = {
        'prompt': prompt,
        'followup': followup,
        'question': context.get('question', ''),
        'recommendations': context.get('recommendations', []),
    }

    # 컨텍스트 합치기 (+ 태그 상태 전달)
    context.update({
        'places': page_obj,
        'place_class': class_filter,
        'tags': tags_qs,
        'match': match_mode,     # 'any' or 'all'
        'selected_tags': selected,
    })

    if context.get('recommended_places') and not context.get('show_followup'):
        from urllib.parse import urlencode
        q = {'prompt': prompt}
        if followup:
            q['followup'] = followup
        return redirect(f"/search/?{urlencode(q)}")

    return render(request, 'places/main.html', context)

def search(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')

    sess = request.session.get('last_reco')
    if sess and sess.get('prompt') == prompt and sess.get('followup') == followup:
        context = build_context_from_cached(prompt, followup, sess, request.user)
    else:
        context = get_recommendation_context(prompt, followup, request.user)

    return render(request, 'search.html', context)

def place_detail(request, pk):
    base = Place.objects.filter(pk=pk)
    if request.user.is_authenticated:
        base = base.annotate(
            is_liked=Exists(PlaceLike.objects.filter(user=request.user, place=OuterRef('pk'))),
            like_count=Count('placelikes', distinct=True),
        )
    else:
        base = base.annotate(
            is_liked=Value(False, output_field=BooleanField()),
            like_count=Count('placelikes', distinct=True),
        )
    place = get_object_or_404(base)
    return render(request, 'places/place_detail.html', {'place': place})

from django.views.decorators.http import require_POST
from django.db import IntegrityError, transaction

@login_required
@require_POST
def toggle_place_like(request, pk):
    place = get_object_or_404(Place, pk=pk)
    user = request.user

    # AJAX 판별 (Django 4+)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # 토글 (경쟁조건 안전)
    try:
        with transaction.atomic():
            obj, created = PlaceLike.objects.get_or_create(user=user, place=place)
            if created:
                liked = True
            else:
                obj.delete()
                liked = False
    except IntegrityError:
        # 극히 드문 경쟁 상황 방지용 리트라이
        liked = PlaceLike.objects.filter(user=user, place=place).exists()
        if liked:
            PlaceLike.objects.filter(user=user, place=place).delete()
            liked = False
        else:
            PlaceLike.objects.create(user=user, place=place)
            liked = True

    data = {
        'liked': liked,
        'like_count': PlaceLike.objects.filter(place=place).count(),
        'place_id': place.id,
    }

    if is_ajax:
        return JsonResponse(data)

    return redirect('places:place_detail', pk=place.id)

def place_list_fragment(request):
    # 원래 main()의 필터 부분 거의 그대로 복사
    class_filter = request.GET.get('place_class', '')
    qs = Place.objects.all().order_by('-id')

    if class_filter and class_filter.isdigit():
        qs = qs.filter(place_class=int(class_filter))

    selected, _match_mode, _raw_tags = _parse_selected_tags(request)
    if selected:
        qs_all = qs
        for tag in selected:
            qs_all = qs_all.filter(tags__name=tag)
        qs_all = qs_all.distinct()

        if qs_all.exists():
            qs = qs_all
        else:
            qs = qs.filter(tags__name__in=selected).distinct()

    qs = with_like_meta(qs, request.user)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'places/_place_items.html', {
        'places': page_obj,
    })
