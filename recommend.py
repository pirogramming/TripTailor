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

index = faiss.read_index("triptailor_cosine_v2.index")
metadata = pd.read_csv("triptailor_full_metadata.csv")

# .env 로드(key 보호)
load_dotenv()

# LLM & prompt
llm = ChatClovaX(
    model="HCX-005",
    temperature=0,
)

extraction_prompt = PromptTemplate.from_template(
    """
    다음 사용자의 문장에서 여행 관련 정보를 정확히 추출해 줘.
    문장: "{input}"

    다음 항목들을 추출해 줘:
    - 지역: 여행하고 싶은 지역 (없으면 "없음")
    - 감정: 원하는 분위기나 감정 (예: 조용한, 힐링, 활기찬 등, 없으면 "없음")
    - 활동: 하고 싶은 활동 (예: 단풍 구경, 산책, 캠핑 등, 없으면 "없음")
    - 태그: 특별한 태그나 키워드 (없으면 "없음")

    만약 지역, 감정, 활동 중 하나라도 "없음"이면 보충 질문을 만들어 주세요.
    모든 정보가 충분하면 보충 질문은 빈 문자열로 해주세요.

    반드시 JSON 형식으로만 출력해 줘:
    {{
    "지역": "추출된 지역",
    "감정": "추출된 감정/분위기",
    "활동": "추출된 활동",
    "태그": "추출된 태그",
    "보충 질문": "보충 질문 또는 빈 문자열"
    }}
    """
)

recommendation_prompt = PromptTemplate.from_template(
    """
    여행지 리스트에서 지역, 감정 또는 분위기, 하고 싶은 활동, 태그와 관련된 여행지를 추천해줘
    여행지 리스트: {trip_spot_list}
    지역: {location}
    감정: {emotion}
    하고 싶은 활동: {activity}
    태그: {tags}

    추천 결과는 다음과 같은 형식으로 간결하게 출력해 줘:

    1. **[여행지명]**
    - 이유: 간단한 추천 이유

    2. **[여행지명]**
    - 이유: 간단한 추천 이유

    최대 3개까지만 추천해 주세요.
    """
)

extraction_chain = extraction_prompt | llm
recommendation_chain = recommendation_prompt | llm


# TypedDict & Graph 구성
class GraphState(TypedDict, total=False):
    user_input: str
    지역: str
    감정: str
    활동: str
    태그: str
    보충_질문: str
    recommendations: List[str]

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
    
    # LLM 응답에서 content 추출
    if hasattr(raw, "content"):
        response_text = raw.content
    else:
        response_text = str(raw)
    
    # JSON 파싱 시도
    try:
        # JSON 블록을 찾아서 파싱
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            parsed = json.loads(json_str)
        else:
            # JSON이 없으면 기본값 설정
            parsed = {
                "지역": "없음",
                "감정": "없음",
                "활동": "없음",
                "태그": "없음",
                "보충 질문": "어떤 지역에서 여행하고 싶으신가요?"
            }
    except json.JSONDecodeError:
        # JSON 파싱 실패시 기본값 설정
        parsed = {
            "지역": "없음",
            "감정": "없음",
            "활동": "없음", 
            "태그": "없음",
            "보충 질문": "어떤 지역에서 여행하고 싶으신가요?"
        }
    
    return {
        **state,
        "지역": parsed.get("지역", ""),
        "감정": parsed.get("감정", ""),
        "활동": parsed.get("활동", ""),
        "태그": parsed.get("태그", ""),
        "보충_질문": parsed.get("보충 질문", "")
    }

def recommend_places(state: GraphState, sample_places=None) -> GraphState:
    embedding = get_clova_embedding(state["user_input"], os.getenv("CLOVASTUDIO_API_KEY"))
    D, I = index.search(np.array([embedding], dtype=np.float32), k=5)
    top_k = metadata.iloc[I[0]]

    trip_spot_list = "\n".join(
        f"- {row['명칭']} ({row['주소']}): {row['개요']}"
        for _, row in top_k.iterrows()
    )

    rec = recommendation_chain.invoke({
        "trip_spot_list": trip_spot_list,
        "location": state["지역"],
        "emotion": state["감정"],
        "activity": state["활동"],
        "tags": state["태그"]
    })

    # LLM 응답에서 content 추출
    if hasattr(rec, "content"):
        response_text = rec.content
    else:
        response_text = str(rec)

    return {
        **state,
        "recommendations": response_text.split("\n")
    }

builder = StateGraph(GraphState)
builder.add_node("extract_info", RunnableLambda(extract_info))
builder.add_node("recommend", RunnableLambda(recommend_places))
builder.set_entry_point("extract_info")
builder.add_edge("extract_info", "recommend")
builder.set_finish_point("recommend")
app = builder.compile()

# 실행

if __name__ == "__main__":
    print("=== TripTailor 여행지 추천 시스템 ===")
    print("원하는 여행 조건을 자유롭게 입력해주세요!")
    print("예시: '강원도에서 가을에 단풍 구경하면서 조용히 힐링할 수 있는 곳을 추천해줘'")
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
            
            print("\n처리 중입니다... 잠시만 기다려주세요.\n")
            
            result = app.invoke({"user_input": user_input})

            if result.get("보충_질문"):
                print("🤔 보충 질문:", result["보충_질문"])
                print("더 구체적으로 답변해주시면 더 정확한 추천을 받으실 수 있습니다.\n")
            else:
                extracted = {k: v for k, v in result.items() if k not in ["recommendations", "user_input"]}
                print("📋 추출된 정보:")
                for key, value in extracted.items():
                    if value:  # 빈 값이 아닌 경우만 출력
                        print(f"  - {key}: {value}")
                
                print("\n🎯 [추천 결과]")
                for line in result["recommendations"]:
                    if line.strip():  # 빈 줄 제외
                        print(line)
            
            print("\n" + "="*50 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n추천 시스템을 종료합니다. 감사합니다!")
            break
        except Exception as e:
            print(f"오류가 발생했습니다: {e}")
            print("다시 시도해주세요.\n")

