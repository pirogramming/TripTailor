import os
import json
import numpy as np
import faiss
from typing import List, TypedDict
from dotenv import load_dotenv

from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_naver import ChatClovaX
from langgraph.graph import StateGraph

# .env 로드(key 보호)
load_dotenv()

# LLM & prompt
llm = ChatClovaX(
    model="HCX-005",
    temperature=0,
    naver_api_key=os.getenv("CLOVA_API_KEY")
)

extraction_prompt = PromptTemplate.from_template(
    """
    다음 사용자의 문장에서 아래 항목들을 정확히 추출해 줘.
    문장: "{input}"

    다음 네 가지 항목을 추출해 줘 (없으면 "없음"이라고 써줘):
    - 지역 (있는 경우): 
    - 감정 또는 분위기 (있는 경우): 
    - 하고 싶은 활동 (있는 경우): 
    - 태그 (있는 경우):

    그리고 위 정보 중(태그 제외) "없음"이 포함되어 있다면, 사용자가 쉽게 응답할 수 있도록 보충 질문을 한 문장으로 만들어 줘.

    출력 예시 (JSON 형식):
    {{
    "지역": "...",
    "감정": "...",
    "활동": "...",
    "태그": "...",
    "보충 질문": "..."
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

    추천 결과는 다음과 같은 형식으로 출력해 줘:

    예시:
    1. **오설록 티뮤지엄**  
    - 이유: 조용한 분위기의 녹차 관련 전시와 힐링 공간이 감정/활동과 잘 어울립니다.

    2. **제주도 해변**  
    - 이유: 탁 트인 바다와 산책로가 있어 "힐링 + 산책" 목적에 적합합니다.
    """
)

extraction_chain = LLMChain(prompt=extraction_prompt, llm=llm)
recommendation_chain = LLMChain(prompt=recommendation_prompt, llm=llm)


# TypedDict & Graph 구성
class GraphState(TypedDict, total=False):
    user_input: str
    지역: str
    감정: str
    활동: str
    태그: str
    보충_질문: str
    recommendations: List[str]

def extract_info(state: GraphState) -> GraphState:
    raw = extraction_chain.run({"input": state["user_input"]})
    parsed = json.loads(raw)
    return {
        **state,
        "지역": parsed.get("지역", ""),
        "감정": parsed.get("감정", ""),
        "활동": parsed.get("활동", ""),
        "태그": parsed.get("태그", ""),
        "보충_질문": parsed.get("보충 질문", "")
    }

def recommend_places(state: GraphState, sample_places=None) -> GraphState:
    rec = recommendation_chain.run({
        "trip_spot_list": sample_places, # 나중에 DB 또는 파일 연결 예정
        "location": state["지역"],
        "emotion": state["감정"],
        "activity": state["활동"],
        "tags": state["태그"]
    })
    return {
        **state,
        "recommendations": rec.split("\n")
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
    result = app.invoke({"user_input": "가을에 단풍 구경하면서 조용히 힐링할 수 있는 곳을 추천해줘"})

    if result.get("보충_질문"):
        print("보충 질문:", result["보충_질문"])
    else:
        extracted = {k: v for k, v in result.items() if k not in ["recommendations"]}
        print("추출된 정보:", extracted)
        print("\n[추천 결과]")
        for line in result["recommendations"]:
            print(line)

