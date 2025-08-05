from django.shortcuts import render
from .models import Place
import recommend
import re

def main(request):
    prompt = request.GET.get('prompt', '')
    places = Place.objects.all()
    recommendations = []
    recommended_places = []

    if prompt:
        print(f"입력된 프롬프트: {prompt}")
        result = recommend.app.invoke({"user_input": prompt})
        print(f"추천 결과: {result}")
        recommendations = result.get("recommendations", [])
        print(f"파싱된 추천: {recommendations}")

        # 여행지명 파싱 (예: "1. **[여행지명]** ..." 형식)
        place_names = []
        for rec in recommendations:
            match = re.search(r"\*\*\[(.+?)\]\*\*", rec)
            if match:
                place_names.append(match.group(1))

        # 실제 Place 객체만 필터링
        if place_names:
            recommended_places = Place.objects.filter(name__in=place_names)

    return render(request, 'places/main.html', {
        'places': places,
        'recommendations': recommendations,
        'recommended_places': recommended_places,
        'prompt': prompt,
    })