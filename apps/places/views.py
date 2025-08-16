from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, BooleanField, Value, Count, Q
from django.http import JsonResponse
from urllib.parse import urlencode
from django.core.paginator import Paginator
import recommend 
from django.core.paginator import Paginator
from .models import Place, PlaceLike, Tag
import re

RECO_TARGET = 6

def _norm_name(s: str) -> str:
    import re
    s = s or ""
    s = re.sub(r"[\s\(\)\[\]「」『』\-_/·•~!@#$%^&*=+|:;\"'<>?,.]+", "", s)
    return s.lower()

def _parse_selected_tags(request):
    raw_list = request.GET.getlist('tags')

    selected = []
    for raw in raw_list:
        if ',' in raw:
            selected += [tag.strip() for tag in raw.split(',')]
        else:
            selected.append(raw.strip())

    # ✅ 중복 제거
    selected = list(dict.fromkeys([tag for tag in selected if tag]))

    match = (request.GET.get('match') or 'any').lower()

    return selected, match, ','.join(selected)


# 1) 더 튼튼한 파서
def parse_recommendations(recommendations):
    """
    recommendations: list[str] (LLM이 반환한 줄 배열)
    반환: [{"name": ..., "reason": ..., "tip": ...}, ...]
    """
    print("\n[DEBUG] raw recommendations:", recommendations)
    parsed = []

    # 1) 패턴들
    inline_pat  = re.compile(r"^\s*\d+\.\s*\*\*\s*\[?([^\]\*]+?)\]?\s*\*\*\s*:\s*(.+?)\s*$")
    bold_pat    = re.compile(r"\*\*\s*\[?([^\]\*]+?)\]?\s*\*\*")
    numline_pat = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")  # 굵게 없을 때

    # 다음 비어있지 않은 줄을 찾는 유틸
    def _is_item_start(s: str) -> bool:
        return bool(re.match(r"^\s*\d+\.\s*", s or ""))

    def _clean(s: str) -> str:
        return (s or "").strip()

    i = 0
    n = len(recommendations)

    while i < n:
        line = _clean(recommendations[i])
        name, reason, tip = None, "", ""

        # --- 케이스 B: 같은 줄에 이유 (e.g., "1. **[이름]**: 이유 ...")
        m_inline = inline_pat.match(line)
        if m_inline:
            name = m_inline.group(1).strip()
            reason = m_inline.group(2).strip()
            # 같은 항목에 이어지는 "팁" 라인이 뒤에 올 수도 있으니 계속 스캔
            j = i + 1
            while j < n:
                cand = _clean(recommendations[j])
                if not cand:  # 빈 줄 스킵
                    j += 1
                    continue
                if _is_item_start(cand):  # 다음 항목 시작 -> stop
                    break
                # 팁 라인 처리
                if cand.startswith("- 구체적인 팁:") or "구체적인 팁:" in cand:
                    tip = cand.split("구체적인 팁:", 1)[-1].strip()
                # 접두 없는데 이유로 볼 수 있는 문장 (reason이 이미 있으면 건너뜀)
                elif not cand.startswith("- ") and not reason:
                    reason = cand
                j += 1

            parsed.append({"name": name, "reason": reason, "tip": tip})
            print(f"[DEBUG] parsed(B): name='{name}', reason='{reason}', tip='{tip}'")
            i = j
            continue

        # --- 케이스 A/C: 이름만 뽑아놓고 뒤 줄들 스캔
        m_bold = bold_pat.search(line)
        if m_bold:
            name = m_bold.group(1).strip()
        else:
            m_num = numline_pat.match(line)
            if m_num:
                name = re.sub(r"^[\-\*\s\[]+|[\]\s]+$", "", m_num.group(1).strip())

        if name:
            # 이름 다음으로 이어지는 블록을 스캔: 다음 번호 항목 시작 전까지
            j = i + 1
            while j < n:
                cand = _clean(recommendations[j])
                if not cand:  # 빈 줄 스킵
                    j += 1
                    continue
                if _is_item_start(cand):  # 다음 항목 시작
                    break

                # 우선순위: 명시적 접두
                if cand.startswith("- 이유:") or "이유:" in cand:
                    # 첫 번째 "이유:"만 채택 (여러 줄이면 첫 것만)
                    if not reason:
                        reason = cand.split("이유:", 1)[-1].strip()

                elif cand.startswith("- 구체적인 팁:") or "구체적인 팁:" in cand:
                    if not tip:
                        tip = cand.split("구체적인 팁:", 1)[-1].strip()

                else:
                    # 접두어 없이 온 문장: reason이 비어있다면 reason으로 간주
                    if not reason and not cand.startswith("- "):
                        reason = cand

                j += 1

            parsed.append({"name": name, "reason": reason, "tip": tip})
            print(f"[DEBUG] parsed(A/C): name='{name}', reason='{reason}', tip='{tip}'")
            i = j
            continue

        # 이름을 못 찾으면 다음 줄로
        i += 1

    print("[DEBUG] final parsed_recs:", parsed)
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
    reason_by_norm = {_norm_name(r["name"]): (r.get("reason") or "") for r in parsed_recs if r.get("name")}
    tip_by_norm    = {_norm_name(r["name"]): (r.get("tip")    or "") for r in parsed_recs if r.get("name")}
    names = [r["name"] for r in parsed_recs if r.get("name")]

    candidates_qs = with_like_meta(find_places_by_names(names), user)
    candidates = list(candidates_qs)  

    name_index = {p.name: p for p in candidates}
    lower_index = [(p.name.lower(), p) for p in candidates]

    for rec in parsed_recs:
        nm = rec["name"]
        nm_norm = _norm_name(nm)
        place = name_index.get(nm) or next((p for name_l, p in lower_index if nm.lower() in name_l), None)
        if place and not any(x["place"].pk == place.pk for x in recommended_places):
            recommended_places.append({"place": place, "reason": reason_by_norm.get(nm_norm, ""), "tip": tip_by_norm.get(_norm_name(nm), "")})

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

    # 모델이 준 추가 이름 병합
    model_names = result.get("추천_장소명") or []
    for n in model_names:
        if n and n not in names:
            names.append(n)

    # 이유 딕셔너리 (정규화 키)
    reason_by_norm = {_norm_name(r["name"]): (r.get("reason") or "") for r in parsed_recs if r.get("name")}
    tip_by_norm    = {_norm_name(r["name"]): (r.get("tip")    or "") for r in parsed_recs if r.get("name")}


    candidates = find_places_by_names(names)
    like_annotated = list(with_like_meta(Place.objects.filter(id__in=[p.id for p in candidates]), user))
    by_id = {p.id: p for p in like_annotated}

    used = set()
    for nm in names:
        # 후보 중 동일/유사 이름 찾기 (기존 로직 유지)
        hit = next((p for p in candidates if p.name == nm), None)
        hit = by_id.get(hit.id) if hit else None
        if hit and hit.id not in used:
            # ✅ 정규화된 이름으로 이유 매칭
            reason = reason_by_norm.get(_norm_name(nm), "")
            tip = tip_by_norm.get(_norm_name(nm), "")

            recommended_places.append({"place": hit, "reason": reason, "tip": tip})
            used.add(hit.id)

    # 부족하면 채우기(이유는 빈 문자열 그대로)
    if len(recommended_places) < RECO_TARGET:
        remain = [p for p in like_annotated if p.id not in used]
        remain.sort(key=lambda x: getattr(x, "like_count", 0), reverse=True)
        for p in remain:
            recommended_places.append({"place": p, "reason": "", "tip": ""})
            used.add(p.id)
            if len(recommended_places) >= RECO_TARGET:
                break

    show_followup = bool(question)
    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places[:RECO_TARGET],  # 최종 RECO_TARGET개 보장
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

    # ✅ 태그 필터 (URL 예: ?tags=레트로&tags=야경&match=any)
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

    # 태그/좋아요 메타
    qs = qs.prefetch_related('tags')
    qs = with_like_meta(qs, request.user)

    # 페이지네이션
    paginator = Paginator(qs, 21)
    page_obj = paginator.get_page(request.GET.get('page'))

    # page 제외 쿼리스트링
    q = request.GET.copy()
    q.pop('page', None)
    base_qs = q.urlencode()
    base_prefix = f"?{base_qs}&" if base_qs else "?"   # 템플릿에서 한 줄로 사용

    # === 페이지 번호 윈도우(5개) ===
    num_pages = page_obj.paginator.num_pages
    cur = page_obj.number
    window = 5
    start = max(1, cur - 2)
    end = min(num_pages, start + window - 1)
    start = max(1, end - window + 1)

    page_window = range(start, end + 1)
    show_first = start > 1
    show_last = end < num_pages
    show_first_ellipsis = start > 2
    show_last_ellipsis = end < (num_pages - 1)

    # 모델 호출 1회
    context = get_recommendation_context(prompt, followup, request.user)

    # 세션 저장
    request.session['last_reco'] = {
        'prompt': prompt,
        'followup': followup,
        'question': context.get('question', ''),
        'recommendations': context.get('recommendations', []),
    }

    # 컨텍스트
    context.update({
        'places': page_obj,             # Page 객체
        'base_qs': base_qs,
        'base_prefix': base_prefix,     # "?...&" 또는 "?"
        'prompt': prompt,
        'followup': followup,
        'place_class': class_filter,
        'tags': Tag.objects.order_by('name'),
        'match': match_mode,            # 'any' or 'all'
        'selected_tags': selected,
        # 페이지네이션 창 관련
        'page_window': page_window,
        'show_first': show_first,
        'show_last': show_last,
        'show_first_ellipsis': show_first_ellipsis,
        'show_last_ellipsis': show_last_ellipsis,
    })

    # 추천 결과 라우팅
    if context.get('recommended_places') and not context.get('show_followup'):
        redir_q = {'prompt': prompt}
        if followup:
            redir_q['followup'] = followup
        return redirect(f"/search/?{urlencode(redir_q)}")

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