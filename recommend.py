import os
import json
import requests
import uuid
import numpy as np
import faiss
import pandas as pd
from typing import List, TypedDict
from dotenv import load_dotenv

from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import PromptTemplate
from langchain_naver import ChatClovaX
from langgraph.graph import StateGraph

# FAISS 인덱스 및 메타데이터 로드
_index = None
_metadata = None

def _load_faiss_and_meta():
    global _index, _metadata
    if _index is not None and _metadata is not None:
        return _index, _metadata
    try:
        import faiss, pandas as pd
        _index = faiss.read_index(os.getenv("FAISS_INDEX_PATH", "triptailor_cosine_v2.index"))
        _metadata = pd.read_csv(os.getenv("FAISS_META_PATH", "triptailor_full_metadata.csv")).fillna("")
        return _index, _metadata
    except Exception as e:
        print(f"[warn] FAISS/CSV load failed: {e}")
        return None, None

# DB 검색 도우미
def search_top_k_from_db(qvec, k=10):
    # ← 함수 내부로 옮기기 (Django가 준비된 뒤 임포트)
    from apps.places.models import Place
    from apps.tags.models import Tag
    from pgvector.django import L2Distance, CosineDistance, MaxInnerProduct

    metric = os.getenv("PGVECTOR_METRIC", "l2")
    if metric == "cosine":
        distance = CosineDistance("embedding", qvec)
    elif metric == "ip":
        distance = MaxInnerProduct("embedding", qvec)
    else:
        distance = L2Distance("embedding", qvec)

    qs = (Place.objects.exclude(embedding=None)
        .annotate(dist=distance)
        .order_by("dist")
        .prefetch_related("tags")[:k])

    return [{
        "명칭": p.name,
        "주소": p.address or "",
        "개요": p.overview or "",
        "tags": [t.name for t in p.tags.all()],
    } for p in qs]


# 환경 변수 로드
load_dotenv()

# LLM 설정
llm = ChatClovaX(
    model="HCX-005",
    temperature=0,
)

# 정보 추출 프롬프트
extraction_prompt = PromptTemplate.from_template(
    """
    다음 사용자의 문장에서 여행 관련 정보를 JSON으로 추출해줘.
    문장: "{input}"

    추출 항목:
    - 지역: 여행하고 싶은 지역 (없으면 "없음")
    - 감정: 원하는 분위기나 감정 (예: 조용한, 힐링, 활기찬 등, 없으면 "없음")
    - 활동: 하고 싶은 활동 (예: 단풍 구경, 산책 등, 없으면 "없음")

    위 3개 중 하나라도 "없음"이면 보충 질문을 추가해줘.
    모두 있다면 보충 질문은 빈 문자열로 해줘.

    출력 형식 (JSON):
    {{
    "지역": "...",
    "감정": "...",
    "활동": "...",
    "보충 질문": "..."
    }}
    """
)

# 추천 프롬프트
recommendation_prompt = PromptTemplate.from_template(
    """
    아래 '여행지 리스트' 중에서만 고르고, 사용자 조건에 맞는 여행지 **정확히 3곳**을 추천하라.
    리스트에 없는 장소명은 절대 쓰지 마라.

    # 출력 형식(반드시 준수)
    1. **[여행지명]**
    - 이유: 두 문장, 80~150자. 첫 문장은 사용자 조건과의 적합성(지역/감정/활동 연결), 
            두 번째 문장은 해당 장소의 주요 특징과 매력을 설명.
    - 구체적인 팁: 방문 시간대, 동선, 준비물, 계절별 추천 활동 등 실질적으로 도움이 되는 팁을 1~2문장으로 제공.

    2. **[여행지명]**
    - 이유: 두 문장, 80~150자.
    - 구체적인 팁: 1~2문장.

    3. **[여행지명]**
    - 이유: 두 문장, 80~150자.
    - 구체적인 팁: 1~2문장.

    # 작성 규칙
    - 태그(예: #힐링, #야경 등)는 절대 언급하지 말 것.
    - 해시태그, 불필요한 마크다운, 이모지, 장식 문자를 사용하지 말 것.
    - 장소명은 반드시 여행지 리스트에 있는 것만 사용.
    - 설명은 자연스럽고 구체적으로 작성하되, 불필요한 수식어나 반복은 피할 것.

    # 사용자 정보
    - 지역: {location}
    - 감정: {emotion}
    - 활동: {activity}
    - 태그 조건: {tags} (참고용이며, 결과 문장에 직접 쓰지 말 것)

    # 여행지 리스트
    {trip_spot_list}
    """
)




extraction_chain = extraction_prompt | llm
recommendation_chain = recommendation_prompt | llm

class GraphState(TypedDict, total=False):
    user_input: str
    지역: str
    감정: str
    활동: str
    태그: str
    보충_질문: str
    recommendations: List[str]
    추천_장소명: List[str]
    장소_태그맵: dict

def get_clova_embedding(text: str, api_key: str) -> List[float]:
    url = "https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4())
    }
    response = requests.post(url, headers=headers, json={"text": text})
    response.raise_for_status()
    return response.json()["result"]["embedding"]

def extract_info(state: GraphState) -> GraphState:
    raw = extraction_chain.invoke({"input": state["user_input"]})
    response_text = getattr(raw, "content", str(raw))
    try:
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        json_str = response_text[start_idx:end_idx]
        parsed = json.loads(json_str)
    except:
        parsed = {"지역": "없음", "감정": "없음", "활동": "없음", "보충 질문": "어디에서 여행하고 싶으신가요?"}

    # 추천 조건이 모두 있을 때만 recommend로 넘김
    need_followup = (
        parsed.get("지역", "없음") == "없음" or
        parsed.get("감정", "없음") == "없음" or
        parsed.get("활동", "없음") == "없음"
    )
    return {
        **state,
        "지역": parsed.get("지역", ""),
        "감정": parsed.get("감정", ""),
        "활동": parsed.get("활동", ""),
        "보충_질문": parsed.get("보충 질문", ""),
        "need_followup": need_followup
    }

def recommend_places(state: GraphState) -> GraphState:
    # 1) 쿼리 임베딩
    embedding = get_clova_embedding(state["user_input"], os.getenv("CLOVASTUDIO_API_KEY"))
    qvec = list(map(float, embedding))  # list[float]

    # 2) DB에서 top-k 시도
    try:
        rows = search_top_k_from_db(qvec, k=10)
    except Exception as e:
        print(f"[warn] DB retrieval failed, fallback to FAISS: {e}")
        rows = None

    if rows is None:
        index, metadata = _load_faiss_and_meta()
        if index is None or metadata is None:
            raise RuntimeError("DB 검색 실패했고 FAISS 리소스도 없습니다.")
        emb_np = np.ascontiguousarray([qvec], dtype=np.float32)
        D, I = index.search(emb_np, k=10)
        top_k = metadata.iloc[I[0]]
        rows = [{
            "명칭": str(row["명칭"]),
            "주소": str(row["주소"]),
            "개요": str(row["개요"]),
            "tags": [str(row.get(c, "")).strip() for c in ["tag1","tag2","tag3","tag4","tag5"] if str(row.get(c, "")).strip()],
        } for _, row in top_k.iterrows()]

    # 4) LLM 입력 리스트 구성
    trip_spot_list = "\n".join(
        f"- {r['명칭']} ({r['주소']}): {r['개요']} [태그: {', '.join(r['tags'])}]"
        for r in rows
    )

    combined_tags = ", ".join(sorted({t for r in rows for t in r["tags"] if t}))

    rec = recommendation_chain.invoke({
        "trip_spot_list": trip_spot_list,
        "location": state["지역"],
        "emotion": state["감정"],
        "activity": state["활동"],
        "tags": combined_tags
    })

    response_text = getattr(rec, "content", str(rec))
    raw_lines = [ln.strip() for ln in response_text.splitlines() if ln.strip()]

    recommended_places = []
    for line in raw_lines:
        if line.strip().startswith(("1.", "2.", "3.")):
            start = line.find("**[") + 3
            end = line.find("]**")
            place_name = line[start:end] if start != -1 and end != -1 else ""
            if place_name:
                recommended_places.append(place_name)

    # 5) 태그 맵 (DB/FAISS 공통)
    place_info_map = {r["명칭"]: r["tags"] for r in rows}

    return {
        **state,
        "recommendations": raw_lines,
        "태그": combined_tags,
        "추천_장소명": recommended_places,
        "장소_태그맵": place_info_map
    }


# StateGraph에서 조건 분기 추가
builder = StateGraph(GraphState)
builder.add_node("extract_info", RunnableLambda(extract_info))
builder.add_node("recommend", RunnableLambda(recommend_places))

# 분기: 보충 질문이 필요하면 recommend로 가지 않음
def should_recommend(state: GraphState):
    return not state.get("need_followup", False)

builder.set_entry_point("extract_info")
builder.add_conditional_edges(
    "extract_info",
    should_recommend,
    {
        True: "recommend",
        False: "extract_info"  # 보충 질문만 반환하고 종료
    }
)
builder.set_finish_point("recommend")
builder.set_finish_point("extract_info")
app = builder.compile()

if __name__ == "__main__":
    print("=== TripTailor 여행지 추천 시스템 ===")
    print("예시: '강원도에서 단풍 구경하면서 조용히 힐링할 수 있는 곳 추천해줘'")
    print("종료하려면 'quit' 또는 'exit'를 입력하세요.\n")

    while True:
        try:
            user_input = input("여행 조건을 입력하세요: ").strip()
            if user_input.lower() in ['quit', 'exit', '종료']:
                print("추천 시스템을 종료합니다. 감사합니다!")
                break
            if not user_input:
                print("입력을 다시 해주세요.\n")
                continue

            state = {"user_input": user_input}
            print("\n처리 중입니다...\n")
            result = app.invoke(state)

            if result.get("보충_질문"):
                print("🤔 보충 질문:", result["보충_질문"])
                followup = input("→ 보충 답변: ").strip()
                full_input = result["user_input"] + " " + followup
                state = {"user_input": full_input}
                print("\n보완된 정보를 기반으로 다시 추천합니다...\n")
                result = app.invoke(state)

            print("📋 추출된 정보:")
            for key in ["지역", "감정", "활동"]:
                if value := result.get(key):
                    print(f"  - {key}: {value}")

            print("\n🎯 [추천 결과]")
            i = 0
            while i < len(result["recommendations"]):
                line = result["recommendations"][i].strip()
                if line.startswith(("1.", "2.", "3.")):
                    print(line)
                    if i + 1 < len(result["recommendations"]):
                        reason_line = result["recommendations"][i + 1].strip()
                        if reason_line.startswith("- 이유:"):
                            print(reason_line)

                    place_name = line[line.find("**[") + 3:line.find("]**")].strip()
                    tag_map = result.get("장소_태그맵", {})
                    best_match = next((name for name in tag_map if place_name in name or name in place_name), None)
                    if best_match:
                        tags = tag_map[best_match]
                        print(f"- 태그: {', '.join(tags) if tags else '(태그 없음)'}")
                    else:
                        print("- 태그: (FAISS 결과 내에서 장소를 찾지 못했습니다)")

                    print()
                i += 1

            print("=" * 50 + "\n")

        except KeyboardInterrupt:
            print("\n\n추천 시스템을 종료합니다. 감사합니다!")
            break
        except Exception as e:
            print(f"오류가 발생했습니다: {e}")
            print("다시 시도해주세요.\n")