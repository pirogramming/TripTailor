from django.shortcuts import render, redirect
import recommend
from .models import Place
import re


def parse_recommendations(recommendations):
    parsed = []
    i = 0
    while i < len(recommendations):
        rec = recommendations[i]
        match = re.search(r"\*\*(?:\[)?(.+?)(?:\])?\*\*", rec)
        if match:
            place_name = match.group(1).strip()
            # 다음 줄이 이유라면 파싱
            reason = ""
            if i + 1 < len(recommendations):
                next_line = recommendations[i + 1].strip()
                if next_line.startswith("- 이유:") or "이유:" in next_line:
                    reason = next_line.split("이유:", 1)[-1].strip()
            parsed.append({"name": place_name, "reason": reason})
        i += 1
    return parsed

def get_recommendation_context(prompt, followup):
    recommended_places = []
    recommendations = []
    question = ""
    show_followup = False

    if prompt:
        user_input = prompt
        if followup:
            user_input += " " + followup
        state = {"user_input": user_input}
        result = recommend.app.invoke(state)
        question = result.get("보충_질문", "")
        recommendations = result.get("recommendations", [])
        parsed_recs = parse_recommendations(recommendations)
        for rec in parsed_recs:
            name = rec["name"]
            reason = rec["reason"]
            place = Place.objects.filter(name=name).first()
            if not place:
                place = Place.objects.filter(name__icontains=name).first()
            if not place:
                place = Place.objects.filter(summary__icontains=name).first()
            if not place:
                place = Place.objects.filter(address__icontains=name).first()
            if place and not any(p["place"] == place for p in recommended_places):
                recommended_places.append({"place": place, "reason": reason})
        show_followup = bool(question)
    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places,
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
    }

def main(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    places = Place.objects.all()
    context = get_recommendation_context(prompt, followup)
    context['places'] = places

    # 추천 결과가 있으면 search로 리다이렉트
    if context['recommended_places'] and not context['show_followup']:
        url = f"/search/?prompt={prompt}"
        if followup:
            url += f"&followup={followup}"
        return redirect(url)
    return render(request, 'places/main.html', context)

def search(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    context = get_recommendation_context(prompt, followup)
    return render(request, 'search.html', context)
