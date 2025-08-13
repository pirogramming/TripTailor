import numpy as np
from typing import List, Dict, Optional, Tuple
from django.db.models import Q, Count
from django.conf import settings
from decouple import config
import os

from .models import Place
from apps.tags.models import Tag


class VectorSearchService:
    """
    pgvector 기반 벡터 검색 + 태그 가중치 재랭킹 서비스
    
    검색 과정:
    1. 쿼리 임베딩 생성
    2. 벡터 유사도로 Top-K 후보 검색 (하드필터: 지역/카테고리/영업여부)
    3. 태그 매칭 점수 계산 (Soft Filter)
    4. 가중치 재랭킹 (cosine + tag_match + popularity)
    5. 최종 결과 반환
    """
    
    def __init__(self):
        self.embedding_model = None
        self._init_embedding_model()
        
        # 가중치 설정 (조정 가능)
        self.weights = {
            'cosine': 0.7,      # 벡터 유사도 가중치
            'tag_match': 0.25,  # 태그 매칭 가중치  
            'popularity': 0.05  # 인기도 가중치
        }
        
    def _init_embedding_model(self):
        """임베딩 모델 초기화 (OpenAI 또는 로컬 모델)"""
        try:
            # OpenAI 사용 (기본)
            api_key = config('OPENAI_API_KEY', default=None)
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
                self.model_name = "text-embedding-3-small"
                print("OpenAI 임베딩 모델 초기화 완료")
                return
                
        except Exception as e:
            print(f"OpenAI 초기화 실패: {e}")
            
        # Fallback: 더미 임베딩 (테스트용)
        print("더미 임베딩 모델 사용 (테스트용)")
        self.client = None
        
    def get_embedding(self, text: str) -> List[float]:
        """텍스트를 임베딩 벡터로 변환"""
        if not text:
            return [0.0] * 1024
            
        try:
            if self.client:
                # OpenAI 임베딩
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=text
                )
                return response.data[0].embedding
            else:
                # 더미 임베딩 (테스트용)
                return self._dummy_embedding(text)
                
        except Exception as e:
            print(f"임베딩 생성 실패: {e}")
            return [0.0] * 1024
            
    def _dummy_embedding(self, text: str) -> List[float]:
        """테스트용 더미 임베딩 생성"""
        import hashlib
        # 텍스트를 해시하여 일관된 더미 벡터 생성
        hash_obj = hashlib.md5(text.encode())
        hash_hex = hash_obj.hexdigest()
        
        # 해시를 기반으로 1024차원 벡터 생성
        np.random.seed(int(hash_hex[:8], 16))
        vector = np.random.normal(0, 1, 1024)
        # 정규화
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()
        
    def extract_tags_from_query(self, query: str) -> List[str]:
        """쿼리에서 태그 자동 추출 (LLM 사용)"""
        try:
            # ClovaX 사용 (기존 코드와 동일)
            api_key = config("CLOVASTUDIO_API_KEY", default=None)
            if api_key:
                os.environ["CLOVASTUDIO_API_KEY"] = api_key
                from langchain_naver import ChatClovaX
                from langchain_core.prompts import PromptTemplate
                
                llm = ChatClovaX(model="HCX-005", temperature=0)
                prompt = PromptTemplate.from_template(
                    "다음 검색어에서 장소 추천에 관련된 키워드 태그를 3-5개 추출해주세요. "
                    "쉼표로 구분해서 답변하세요:\n{query}"
                )
                out = (prompt | llm).invoke({"query": query})
                tags_text = getattr(out, "content", str(out)).strip()
                
                # 쉼표로 분리하고 정리
                tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
                return tags[:5]  # 최대 5개
                
        except Exception as e:
            print(f"태그 자동 추출 실패: {e}")
            
        # Fallback: 간단한 키워드 추출
        return self._simple_tag_extraction(query)
        
    def _simple_tag_extraction(self, query: str) -> List[str]:
        """간단한 키워드 추출 (Fallback)"""
        import re
        stop_words = {
            '에서', '을', '를', '이', '가', '의', '에', '로', '으로', '와', '과',
            '추천', '좋은', '맛있는', '예쁜', '깨끗한', '편한', '가까운'
        }
        
        # 한글, 영문, 숫자만 추출
        words = re.findall(r'[가-힣a-zA-Z0-9]+', query.lower())
        # 불용어 제거 및 길이 필터링
        keywords = [word for word in words if word not in stop_words and len(word) > 1]
        
        return keywords[:5]
        
    def calculate_tag_similarity(self, query_tags: List[str], place_tags: List[str]) -> float:
        """태그 유사도 계산 (Jaccard Similarity)"""
        if not query_tags or not place_tags:
            return 0.0
            
        # 태그 이름으로 변환
        place_tag_names = [tag.name for tag in place_tags]
        
        # Jaccard Similarity 계산
        query_set = set(query_tags)
        place_set = set(place_tag_names)
        
        intersection = len(query_set & place_set)
        union = len(query_set | place_set)
        
        if union == 0:
            return 0.0
            
        return intersection / union
        
    def calculate_popularity_score(self, place: Place) -> float:
        """인기도 점수 계산"""
        try:
            # 좋아요 수 기반 인기도
            like_count = place.placelikes.count()
            
            # 리뷰 수 기반 인기도 (리뷰 모델이 있다면)
            review_count = 0
            if hasattr(place, 'reviews'):
                review_count = place.reviews.count()
                
            # 정규화된 점수 (0~1)
            popularity = min(1.0, (like_count + review_count * 2) / 100)
            return popularity
            
        except Exception:
            return 0.0
            
    def search_places(
        self, 
        query: str, 
        user_tags: Optional[List[str]] = None,
        region: Optional[str] = None,
        place_class: Optional[int] = None,
        limit: int = 20,
        top_k: int = 200
    ) -> List[Dict]:
        """
        메인 검색 함수
        
        Args:
            query: 사용자 검색어
            user_tags: 사용자가 선택한 태그들
            region: 지역 필터
            place_class: 장소 카테고리 필터
            limit: 최종 반환 개수
            top_k: 벡터 검색 후보 개수
            
        Returns:
            재랭킹된 장소 목록
        """
        
        # 1. 태그 처리
        if user_tags:
            query_tags = user_tags
        else:
            query_tags = self.extract_tags_from_query(query)
            
        print(f"검색 태그: {query_tags}")
        
        # 2. 쿼리 임베딩 생성
        query_embedding = self.get_embedding(query)
        
        # 3. 벡터 검색 (Top-K 후보)
        candidates = self._vector_search(
            query_embedding, 
            region=region, 
            place_class=place_class, 
            top_k=top_k
        )
        
        if not candidates:
            print("벡터 검색 결과 없음")
            return []
            
        # 4. 재랭킹
        ranked_results = self._rerank_candidates(
            candidates, query_tags, query_embedding
        )
        
        # 5. 최종 결과 반환
        return ranked_results[:limit]
        
    def _vector_search(
        self, 
        query_embedding: List[float], 
        region: Optional[str] = None,
        place_class: Optional[int] = None,
        top_k: int = 200
    ) -> List[Place]:
        """pgvector를 사용한 벡터 검색"""
        
        # 기본 쿼리 (임베딩이 있는 장소만)
        queryset = Place.objects.filter(embedding__isnull=False)
        
        # 하드 필터 적용
        if region:
            queryset = queryset.filter(region=region)
        if place_class is not None:
            queryset = queryset.filter(place_class=place_class)
            
        # 벡터 유사도 검색
        try:
            # pgvector의 올바른 문법 사용
            from django.db.models import F
            from pgvector.django import CosineDistance
            
            candidates = list(
                queryset.annotate(
                    distance=CosineDistance('embedding', query_embedding)
                ).order_by('distance')[:top_k]
            )
            
            print(f"벡터 검색 완료: {len(candidates)}개 후보")
            return candidates
            
        except Exception as e:
            print(f"벡터 검색 실패: {e}")
            # Fallback: 일반 텍스트 검색
            return self._fallback_text_search(region, place_class, top_k)
            
    def _fallback_text_search(
        self, 
        region: Optional[str] = None,
        place_class: Optional[int] = None,
        limit: int = 200
    ) -> List[Place]:
        """벡터 검색 실패 시 텍스트 검색으로 Fallback"""
        queryset = Place.objects.all()
        
        if region:
            queryset = queryset.filter(region=region)
        if place_class is not None:
            queryset = queryset.filter(place_class=place_class)
            
        return list(queryset.order_by('-id')[:limit])
        
    def _rerank_candidates(
        self, 
        candidates: List[Place], 
        query_tags: List[str], 
        query_embedding: List[float]
    ) -> List[Dict]:
        """후보들을 재랭킹"""
        
        results = []
        
        for place in candidates:
            # 1. 코사인 유사도 (이미 계산됨)
            cosine_score = 1.0 - getattr(place, 'distance', 0.0)
            
            # 2. 태그 매칭 점수
            tag_score = self.calculate_tag_similarity(query_tags, list(place.tags.all()))
            
            # 3. 인기도 점수
            popularity_score = self.calculate_popularity_score(place)
            
            # 4. 가중 평균 계산
            final_score = (
                self.weights['cosine'] * cosine_score +
                self.weights['tag_match'] * tag_score +
                self.weights['popularity'] * popularity_score
            )
            
            # 5. 결과 구성
            result = {
                'place': place,
                'score': final_score,
                'cosine_score': cosine_score,
                'tag_score': tag_score,
                'popularity_score': popularity_score,
                'tags': [tag.name for tag in place.tags.all()],
                'name': place.name,
                'address': place.address,
                'region': place.region,
                'overview': place.overview,
                'summary': place.summary,
                'lat': float(place.lat),
                'lng': float(place.lng),
                'place_class': place.place_class
            }
            
            results.append(result)
            
        # 점수 기준 내림차순 정렬
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"재랭킹 완료: {len(results)}개 결과")
        return results
        
    def update_place_embeddings(self, place_ids: Optional[List[int]] = None):
        """장소들의 임베딩 벡터 업데이트"""
        
        if place_ids:
            places = Place.objects.filter(id__in=place_ids)
        else:
            places = Place.objects.all()
            
        updated_count = 0
        
        for place in places:
            try:
                # 장소 설명 텍스트 구성
                text_parts = []
                if place.name:
                    text_parts.append(place.name)
                if place.overview:
                    text_parts.append(place.overview)
                if place.summary:
                    text_parts.append(place.summary)
                    
                # 태그 정보 추가
                tag_names = [tag.name for tag in place.tags.all()]
                if tag_names:
                    text_parts.append(" ".join(tag_names))
                    
                # 전체 텍스트로 임베딩 생성
                full_text = " ".join(text_parts)
                if full_text.strip():
                    embedding = self.get_embedding(full_text)
                    place.embedding = embedding
                    place.save(update_fields=['embedding'])
                    updated_count += 1
                    
            except Exception as e:
                print(f"장소 {place.id} 임베딩 업데이트 실패: {e}")
                
        print(f"임베딩 업데이트 완료: {updated_count}개 장소")
        return updated_count
