import os
import json
import requests
import uuid
import numpy as np
import faiss
import pandas as pd
from typing import List, Dict, Tuple, Optional, TypedDict
from dotenv import load_dotenv
from dataclasses import dataclass
from collections import defaultdict
import math

from langchain_core.prompts import PromptTemplate
from langchain_naver import ChatClovaX

# 환경 변수 로드
load_dotenv()

# LLM 설정
llm = ChatClovaX(
    model="HCX-005",
    temperature=0,
)

# 태그 자동 추출 프롬프트
tag_extraction_prompt = PromptTemplate.from_template(
    """
    다음 사용자의 여행 요청에서 관련 태그를 추출해주세요.
    
    요청: "{user_input}"
    
    다음 카테고리에서 관련 태그를 찾아주세요:
    - 지역: 서울, 부산, 제주도, 강원도 등
    - 활동: 산책, 등산, 맛집, 카페, 문화시설, 쇼핑, 레포츠 등
    - 분위기: 조용한, 활기찬, 힐링, 로맨틱, 가족친화적 등
    - 계절: 봄, 여름, 가을, 겨울
    - 시간: 아침, 점심, 저녁, 야경 등
    
    JSON 형식으로 출력:
    {{
        "tags": ["태그1", "태그2", "태그3"],
        "region": "지역명 또는 빈 문자열",
        "activity": "주요 활동 또는 빈 문자열"
    }}
    
    태그는 3-8개 정도로 추출하고, 사용자가 명시하지 않은 것은 추측하지 마세요.
    """
)

@dataclass
class SearchResult:
    place_id: int
    name: str
    address: str
    region: str
    overview: str
    tags: List[str]
    place_class: int
    lat: float
    lng: float
    vector_score: float
    tag_score: float
    popularity_score: float
    final_score: float
    reason: str = ""

class AdvancedRecommendationEngine:
    def __init__(self):
        # FAISS 인덱스 및 메타데이터 로드
        try:
            self.index = faiss.read_index("triptailor_cosine_v2.index")
            self.metadata = pd.read_csv("triptailor_full_metadata.csv").fillna("")
            print("Using real FAISS index and metadata")
        except:
            print("Warning: FAISS index or metadata not found. Using dummy data.")
            self.index = None
            # 더미 데이터 생성
            dummy_data = []
            for i in range(1, 101):  # 100개의 더미 장소 생성
                dummy_data.append({
                    '명칭': f'테스트 장소 {i}',
                    '주소': f'테스트 주소 {i}',
                    '지역': ['서울', '부산', '제주', '강원', '경기'][i % 5],
                    '개요': f'테스트 장소 {i}의 상세한 설명입니다. 이 장소는 테스트 목적으로 만들어진 가상의 여행지입니다.',
                    'tag1': ['자연', '문화', '레포츠', '쇼핑', '맛집'][i % 5],
                    'tag2': ['힐링', '관광', '등산', '카페', '문화'][i % 5],
                    'tag3': ['산책', '역사', '바다', '힐링', '맛집'][i % 5],
                    'place_class': (i % 4) + 1,
                    'lat': 37.5665 + (i * 0.001),
                    'lng': 126.9780 + (i * 0.001)
                })
            self.metadata = pd.DataFrame(dummy_data)
        
        # 가중치 설정
        self.alpha = 0.7      # 벡터 유사도 가중치
        self.beta = 0.25      # 태그 매칭 가중치
        self.gamma = 0.05     # 인기도 가중치
        
        # 검색 파라미터
        self.initial_k = 200  # 초기 벡터 검색 결과 수
        self.max_k = 1000     # 최대 확장 가능한 K
        
    def get_clova_embedding(self, text: str) -> List[float]:
        """Clova Studio API로 텍스트 임베딩 생성"""
        api_key = os.getenv("CLOVASTUDIO_API_KEY")
        if not api_key:
            raise ValueError("CLOVASTUDIO_API_KEY not found")
            
        url = "https://clovastudio.stream.ntruss.com/v1/api-tools/embedding/v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4())
        }
        response = requests.post(url, headers=headers, json={"text": text})
        response.raise_for_status()
        return response.json()["result"]["embedding"]
    
    def extract_tags_with_llm(self, user_input: str) -> Dict:
        """LLM을 사용하여 사용자 입력에서 태그 자동 추출"""
        try:
            prompt = tag_extraction_prompt.format(user_input=user_input)
            response = llm.invoke(prompt)
            response_text = getattr(response, "content", str(response))
            
            # JSON 파싱
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                return {
                    "tags": result.get("tags", []),
                    "region": result.get("region", ""),
                    "activity": result.get("activity", "")
                }
        except Exception as e:
            print(f"Tag extraction failed: {e}")
        
        return {"tags": [], "region": "", "activity": ""}
    
    def vector_search(self, query_embedding: List[float], k: int = 200) -> Tuple[np.ndarray, np.ndarray]:
        """FAISS를 사용한 벡터 검색"""
        if self.index is None:
            # 더미 데이터를 사용할 때는 랜덤 결과 반환
            total_items = len(self.metadata)
            k = min(k, total_items)
            indices = np.random.choice(total_items, k, replace=False)
            distances = np.random.random(k) * 0.1  # 작은 거리값
            return distances, indices
            
        embedding = np.ascontiguousarray([query_embedding], dtype=np.float32)
        D, I = self.index.search(embedding, k)
        return D[0], I[0]  # 거리, 인덱스
    
    def calculate_tag_score(self, user_tags: List[str], place_tags: List[str]) -> float:
        """태그 매칭 점수 계산 (Jaccard 유사도 기반)"""
        if not user_tags or not place_tags:
            return 0.0
            
        user_set = set(tag.lower().strip() for tag in user_tags if tag)
        place_set = set(tag.lower().strip() for tag in place_tags if tag)
        
        if not user_set or not place_set:
            return 0.0
            
        intersection = len(user_set & place_set)
        union = len(user_set | place_set)
        
        return intersection / union if union > 0 else 0.0
    
    def calculate_popularity_score(self, place_data: pd.Series) -> float:
        """인기도 점수 계산 (좋아요 수, 리뷰 수 등 기반)"""
        # 여기서는 간단한 예시, 실제로는 PlaceLike, Review 모델 데이터 사용
        return 0.5  # 기본값
    
    def apply_hard_filters(self, candidates: List[SearchResult], 
                          region: str = "", place_class: int = None) -> List[SearchResult]:
        """하드 필터 적용 (지역, 카테고리 등)"""
        filtered = []
        
        for candidate in candidates:
            # 지역 필터
            if region and region not in candidate.region:
                continue
                
            # 카테고리 필터
            if place_class is not None and candidate.place_class != place_class:
                continue
                
            filtered.append(candidate)
            
        return filtered
    
    def calculate_final_score(self, result: SearchResult) -> float:
        """최종 점수 계산"""
        return (self.alpha * result.vector_score + 
                self.beta * result.tag_score + 
                self.gamma * result.popularity_score)
    
    def apply_mmr(self, results: List[SearchResult], lambda_param: float = 0.5) -> List[SearchResult]:
        """MMR (Maximal Marginal Relevance) 적용으로 다양성 확보"""
        if len(results) <= 1:
            return results
            
        selected = [results[0]]
        remaining = results[1:]
        
        while remaining and len(selected) < len(results):
            mmr_scores = []
            
            for candidate in remaining:
                # 관련성 점수 (기존 선택된 항목들과의 평균 유사도)
                relevance = candidate.final_score
                
                # 다양성 점수 (기존 선택된 항목들과의 최소 유사도)
                diversity = min(
                    self.calculate_tag_score(candidate.tags, selected_item.tags)
                    for selected_item in selected
                )
                
                # MMR 점수
                mmr_score = lambda_param * relevance + (1 - lambda_param) * diversity
                mmr_scores.append((mmr_score, candidate))
            
            # 최고 MMR 점수를 가진 항목 선택
            best_score, best_candidate = max(mmr_scores, key=lambda x: x[0])
            selected.append(best_candidate)
            remaining.remove(best_candidate)
        
        return selected
    
    def search_and_rerank(self, user_input: str, user_tags: List[str] = None, 
                         region: str = "", place_class: int = None, 
                         page: int = 1, page_size: int = 20) -> Dict:
        """메인 검색 및 재랭킹 함수"""
        
        # 1. 사용자 입력에서 태그 자동 추출 (사용자가 태그를 제공하지 않은 경우)
        if not user_tags:
            extracted = self.extract_tags_with_llm(user_input)
            user_tags = extracted.get("tags", [])
            if not region and extracted.get("region"):
                region = extracted.get("region")
        
        print(f"Extracted tags: {user_tags}")
        print(f"Extracted region: {region}")
        
        # 2. 벡터 검색으로 후보 추출
        try:
            query_embedding = self.get_clova_embedding(user_input)
            distances, indices = self.vector_search(query_embedding, self.initial_k)
        except Exception as e:
            print(f"Vector search failed: {e}")
            return {"results": [], "total": 0, "page": page, "has_next": False}
        
        # 3. 후보 데이터 구성
        candidates = []
        for i, (distance, idx) in enumerate(zip(distances, indices)):
            if idx >= len(self.metadata):
                continue
                
            row = self.metadata.iloc[idx]
            
            # 태그 정보 추출
            place_tags = []
            for col in ['tag1', 'tag2', 'tag3', 'tag4', 'tag5']:
                if col in row and pd.notna(row[col]) and str(row[col]).strip():
                    place_tags.append(str(row[col]).strip())
            
            # 벡터 점수 (거리를 점수로 변환)
            vector_score = 1.0 / (1.0 + distance)
            
            # 태그 점수
            tag_score = self.calculate_tag_score(user_tags, place_tags)
            
            # 인기도 점수
            popularity_score = self.calculate_popularity_score(row)
            
            candidate = SearchResult(
                place_id=i,
                name=str(row.get('명칭', '')),
                address=str(row.get('주소', '')),
                region=str(row.get('지역', '')),
                overview=str(row.get('개요', '')),
                tags=place_tags,
                place_class=int(row.get('place_class', 0)),
                lat=float(row.get('lat', 0)),
                lng=float(row.get('lng', 0)),
                vector_score=vector_score,
                tag_score=tag_score,
                popularity_score=popularity_score,
                final_score=0.0
            )
            
            candidates.append(candidate)
        
        # 4. 하드 필터 적용
        candidates = self.apply_hard_filters(candidates, region, place_class)
        
        # 5. 최종 점수 계산
        for candidate in candidates:
            candidate.final_score = self.calculate_final_score(candidate)
        
        # 6. 점수순 정렬
        candidates.sort(key=lambda x: x.final_score, reverse=True)
        
        # 7. 최소 점수 필터링 (너무 낮은 점수는 제외)
        min_score_threshold = 0.05  # 더 엄격한 임계값
        candidates = [c for c in candidates if c.final_score >= min_score_threshold]
        
        # 태그 매칭이 있는 결과만 우선 선택
        candidates_with_tags = [c for c in candidates if c.tag_score > 0]
        candidates_without_tags = [c for c in candidates if c.tag_score == 0]
        
        # 태그 매칭이 있는 결과를 먼저, 그 다음에 벡터 점수만 높은 결과를 추가
        candidates = candidates_with_tags + candidates_without_tags[:50]  # 벡터 점수만 높은 결과는 최대 50개만
        
        # 8. MMR 적용 (다양성 확보)
        candidates = self.apply_mmr(candidates)
        
        # 9. 페이지네이션
        total = len(candidates)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_results = candidates[start_idx:end_idx]
        
        print(f"Total candidates after filtering: {total}")
        print(f"Page {page} results: {len(page_results)}")
        
        return {
            "results": page_results,
            "total": total,
            "page": page,
            "has_next": end_idx < total,
            "total_pages": math.ceil(total / page_size),
            "user_tags": user_tags,
            "extracted_region": region
        }

# 전역 인스턴스
recommendation_engine = AdvancedRecommendationEngine()

# 기존 인터페이스와의 호환성을 위한 래퍼 함수
def get_recommendations(user_input: str, user_tags: List[str] = None, 
                       region: str = "", place_class: int = None,
                       page: int = 1, page_size: int = 20) -> Dict:
    """기존 코드와의 호환성을 위한 래퍼 함수"""
    return recommendation_engine.search_and_rerank(
        user_input, user_tags, region, place_class, page, page_size
    )

# 기존 app 인터페이스 유지 (하위 호환성)
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

def extract_info(state: GraphState) -> GraphState:
    """기존 호환성 함수"""
    extracted = recommendation_engine.extract_tags_with_llm(state["user_input"])
    
    # 기존 형식으로 변환
    region = extracted.get("region", "")
    activity = extracted.get("activity", "")
    tags = ", ".join(extracted.get("tags", []))
    
    need_followup = not region or not activity
    
    return {
        **state,
        "지역": region,
        "활동": activity,
        "태그": tags,
        "보충_질문": "더 구체적인 정보를 입력해주세요." if need_followup else "",
        "need_followup": need_followup
    }

def recommend_places(state: GraphState) -> GraphState:
    """기존 호환성 함수"""
    results = recommendation_engine.search_and_rerank(
        state["user_input"], 
        page=1, 
        page_size=3
    )
    
    # 기존 형식으로 변환
    recommendations = []
    추천_장소명 = []
    장소_태그맵 = {}
    
    for i, result in enumerate(results["results"][:3], 1):
        place_name = result.name
        추천_장소명.append(place_name)
        장소_태그맵[place_name] = result.tags
        
        recommendations.append(f"{i}. **[{place_name}]**")
        recommendations.append(f"- 이유: {result.overview[:100]}...")
    
    return {
        **state,
        "recommendations": recommendations,
        "추천_장소명": 추천_장소명,
        "장소_태그맵": 장소_태그맵
    }

# 기존 StateGraph 구조 유지
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph

builder = StateGraph(GraphState)
builder.add_node("extract_info", RunnableLambda(extract_info))
builder.add_node("recommend", RunnableLambda(recommend_places))

def should_recommend(state: GraphState):
    return not state.get("need_followup", False)

builder.set_entry_point("extract_info")
builder.add_conditional_edges(
    "extract_info",
    should_recommend,
    {
        True: "recommend",
        False: "extract_info"
    }
)
builder.set_finish_point("recommend")
builder.set_finish_point("extract_info")

app = builder.compile()

if __name__ == "__main__":
    print("=== TripTailor 고급 추천 시스템 ===")
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

            print("\n처리 중입니다...\n")
            
            # 새로운 엔진 사용
            results = recommendation_engine.search_and_rerank(user_input, page=1, page_size=5)
            
            if results["results"]:
                print(f"🎯 추천 결과 (총 {results['total']}개)")
                print(f"📍 추출된 지역: {results['extracted_region'] or '지정되지 않음'}")
                print(f"🏷️  추출된 태그: {', '.join(results['user_tags'])}")
                print()
                
                for i, result in enumerate(results["results"], 1):
                    print(f"{i}. **{result.name}**")
                    print(f"   📍 {result.address}")
                    print(f"   🏷️  {', '.join(result.tags) if result.tags else '태그 없음'}")
                    print(f"   📊 최종점수: {result.final_score:.3f}")
                    print(f"   💡 {result.overview[:100]}...")
                    print()
            else:
                print("😔 추천 결과를 찾을 수 없습니다.")
                print("더 구체적인 조건을 입력해보세요.")

            print("=" * 50 + "\n")

        except KeyboardInterrupt:
            print("\n\n추천 시스템을 종료합니다. 감사합니다!")
            break
        except Exception as e:
            print(f"오류가 발생했습니다: {e}")
            print("다시 시도해주세요.\n")
