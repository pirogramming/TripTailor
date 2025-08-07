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
index = faiss.read_index("triptailor_cosine_v2.index")
metadata = pd.read_csv("triptailor_full_metadata.csv").fillna("")  # NaN 제거

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
    다음 여행지 리스트를 참고해서 사용자에게 맞는 여행지 3곳을 추천해줘.

    여행지 리스트:
    {trip_spot_list}

    사용자 정보:
    - 지역: {location}
    - 감정: {emotion}
    - 활동: {activity}
    - 태그: {tags}

    출력 형식:
    1. **[여행지명]**
    - 이유: 간단한 이유

    2. **[여행지명]**
    - 이유: 간단한 이유

    최대 3개까지만 추천해줘.
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
    embedding = get_clova_embedding(state["user_input"], os.getenv("CLOVASTUDIO_API_KEY"))
    embedding = np.ascontiguousarray([embedding], dtype=np.float32)
    D, I = index.search(embedding, k=5)
    top_k = metadata.iloc[I[0]]

    trip_spot_list = "\n".join(
        f"- {row['명칭']} ({row['주소']}): {row['개요']} [태그: {', '.join(str(row.get(col, '')).strip() for col in ['tag1','tag2','tag3','tag4','tag5'])}]"
        for _, row in top_k.iterrows()
    )

    combined_tags = ", ".join(
        sorted(set(
            tag
            for _, row in top_k.iterrows()
            for tag in [row.get('tag1'), row.get('tag2'), row.get('tag3'), row.get('tag4'), row.get('tag5')]
            if isinstance(tag, str) and tag.strip()
        ))
    )

    rec = recommendation_chain.invoke({
        "trip_spot_list": trip_spot_list,
        "location": state["지역"],
        "emotion": state["감정"],
        "activity": state["활동"],
        "tags": combined_tags
    })

    response_text = getattr(rec, "content", str(rec))
    raw_lines = response_text.strip().split("\n")

    recommended_places = []
    for line in raw_lines:
        if line.strip().startswith(("1.", "2.", "3.")):
            start = line.find("**[") + 3
            end = line.find("]**")
            place_name = line[start:end] if start != -1 and end != -1 else ""
            if place_name:
                recommended_places.append(place_name)

    place_info_map = {}
    for _, row in top_k.iterrows():
        name = str(row['명칭']).strip()
        tags = [str(row.get(col, '')).strip() for col in ['tag1','tag2','tag3','tag4','tag5']]
        tags = [f"{tag}" for tag in tags if tag]
        place_info_map[name] = tags

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