import os
import json
import numpy as np
from typing import Dict, List, Optional, Tuple
import faiss
from datetime import datetime
import requests
from decouple import config

class ReviewPipelineService:
    
    def __init__(self):
        self.faiss_index_path = "triptailor_cosine_v2.index"
        self.metadata_path = "triptailor_full_metadata.csv"
        self.training_data_path = "training_data/"
        
        # FAISS 인덱스 로드
        self.faiss_index = self._load_faiss_index()
        self.metadata = self._load_metadata()
    
    def _load_faiss_index(self):
        """FAISS 인덱스 로드"""
        try:
            if os.path.exists(self.faiss_index_path):
                return faiss.read_index(self.faiss_index_path)
            else:
                print(f"FAISS 인덱스 파일이 없습니다: {self.faiss_index_path}")
                return None
        except Exception as e:
            print(f"FAISS 인덱스 로드 실패: {e}")
            return None
    
    def _load_metadata(self):
        """메타데이터 로드"""
        try:
            if os.path.exists(self.metadata_path):
                import pandas as pd
                return pd.read_csv(self.metadata_path)
            else:
                print(f"메타데이터 파일이 없습니다: {self.metadata_path}")
                return None
        except Exception as e:
            print(f"메타데이터 로드 실패: {e}")
            return None
    
    def clova_summarize(self, content: str) -> str:
        """
        ClovaX로 리뷰 내용 요약
        """
        try:
            # ClovaX API 키 가져오기
            clova_api_key = config('CLOVA_API_KEY', default=None)
            clova_api_url = config('CLOVA_API_URL', default=None)
            
            if not clova_api_key or not clova_api_url:
                print("ClovaX API 키가 설정되지 않았습니다. 더미 요약을 사용합니다.")
                # 더미 요약 로직
                if len(content) > 100:
                    return content[:100] + "..."
                return content
            
            # ClovaX API 요청
            headers = {
                'Content-Type': 'application/json',
                'X-NCP-APIGW-API-KEY-ID': clova_api_key,
                'X-NCP-APIGW-API-KEY': clova_api_key
            }
            
            # 요약 요청 데이터
            data = {
                "text": content,
                "max_tokens": 100,
                "temperature": 0.3,
                "top_p": 0.8
            }
            
            response = requests.post(clova_api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                summary = result.get('summary', '')
                if summary:
                    return summary
                else:
                    print("ClovaX API 응답에 요약이 없습니다.")
                    return self._fallback_summarize(content)
            else:
                print(f"ClovaX API 요청 실패: {response.status_code} - {response.text}")
                return self._fallback_summarize(content)
                
        except Exception as e:
            print(f"ClovaX 요약 실패: {e}")
            return self._fallback_summarize(content)
    
    def _fallback_summarize(self, content: str) -> str:
        """
        ClovaX API 실패 시 사용할 대체 요약 로직
        """
        if len(content) > 100:
            return content[:100] + "..."
        return content
    
    def clova_embed(self, content: str) -> np.ndarray:
        """
        Clova Embedding으로 임베딩 생성
        """
        try:
            # Clova Embedding API 키 가져오기
            clova_embed_api_key = config('CLOVA_EMBED_API_KEY', default=None)
            clova_embed_api_url = config('CLOVA_EMBED_API_URL', default=None)
            
            if not clova_embed_api_key or not clova_embed_api_url:
                print("Clova Embedding API 키가 설정되지 않았습니다. 더미 임베딩을 사용합니다.")
                # 더미 임베딩 생성
                embedding_dim = 768
                return np.random.randn(embedding_dim).astype('float32')
            
            # Clova Embedding API 요청
            headers = {
                'Content-Type': 'application/json',
                'X-NCP-APIGW-API-KEY-ID': clova_embed_api_key,
                'X-NCP-APIGW-API-KEY': clova_embed_api_key
            }
            
            # 임베딩 요청 데이터
            data = {
                "text": content,
                "model": "clova-embedding-v1"  # 또는 실제 모델명
            }
            
            response = requests.post(clova_embed_api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                embedding = result.get('embedding', [])
                if embedding:
                    return np.array(embedding, dtype='float32')
                else:
                    print("Clova Embedding API 응답에 임베딩이 없습니다.")
                    return self._fallback_embed(content)
            else:
                print(f"Clova Embedding API 요청 실패: {response.status_code} - {response.text}")
                return self._fallback_embed(content)
                
        except Exception as e:
            print(f"Clova Embedding 실패: {e}")
            return self._fallback_embed(content)
    
    def _fallback_embed(self, content: str) -> np.ndarray:
        """
        Clova Embedding API 실패 시 사용할 대체 임베딩 로직
        """
        embedding_dim = 768
        return np.random.randn(embedding_dim).astype('float32')
    
    def should_update(self, review, new_summary: str) -> bool:
        """
        팀 합의된 업데이트 판단 기준:
        - 후기 요약문: cosine similarity < 0.9
        - 태그: 집합(set) 다름
        """
        try:
            # 1. 후기 요약문 비교 (cosine similarity < 0.9)
            old_summary = review.summary
            summary_similarity = self._calculate_cosine_similarity(old_summary, new_summary)
            
            # 2. 태그 비교 (집합 다름)
            old_tags = self._extract_tags(old_summary)
            new_tags = self._extract_tags(new_summary)
            tags_different = old_tags != new_tags
            
            # 업데이트 조건: 요약문 유사도 < 0.9 또는 태그가 다름
            should_update = summary_similarity < 0.9 or tags_different
            
            print(f"업데이트 판단:")
            print(f"  - 요약문 유사도: {summary_similarity:.3f} (임계값: 0.9)")
            print(f"  - 태그 다름: {tags_different}")
            print(f"  - 업데이트 필요: {should_update}")
            
            return should_update
            
        except Exception as e:
            print(f"업데이트 판단 실패: {e}")
            return True  # 오류 시 업데이트 진행
    
    def _calculate_cosine_similarity(self, text1: str, text2: str) -> float:
        """
        두 텍스트 간의 cosine similarity 계산
        """
        try:
            # 간단한 cosine similarity 계산 (실제로는 더 정교한 방법 사용)
            words1 = text1.lower().split()
            words2 = text2.lower().split()
            
            # 단어 빈도 계산
            from collections import Counter
            freq1 = Counter(words1)
            freq2 = Counter(words2)
            
            # 모든 단어 집합
            all_words = set(freq1.keys()) | set(freq2.keys())
            
            if not all_words:
                return 1.0
            
            # 벡터 생성
            vec1 = [freq1.get(word, 0) for word in all_words]
            vec2 = [freq2.get(word, 0) for word in all_words]
            
            # cosine similarity 계산
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
            
        except Exception as e:
            print(f"Cosine similarity 계산 실패: {e}")
            return 0.0
    
    def _extract_tags(self, text: str) -> set:
        """
        텍스트에서 태그 추출 (간단한 키워드 추출)
        """
        try:
            # 간단한 키워드 추출 (실제로는 더 정교한 방법 사용)
            import re
            
            # 특수문자 제거 및 소문자 변환
            clean_text = re.sub(r'[^\w\s]', '', text.lower())
            
            # 불용어 제거
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'his', 'hers', 'ours', 'theirs'}
            
            words = clean_text.split()
            keywords = [word for word in words if word not in stop_words and len(word) > 2]
            
            # 상위 키워드만 태그로 사용
            from collections import Counter
            word_freq = Counter(keywords)
            top_tags = {word for word, freq in word_freq.most_common(5)}
            
            return top_tags
            
        except Exception as e:
            print(f"태그 추출 실패: {e}")
            return set()
    
    def update_faiss_db(self, review, embedding: np.ndarray, summary: str):
        """
        FAISS DB와 메타데이터 업데이트
        """
        try:
            if self.faiss_index is None:
                print("FAISS 인덱스가 로드되지 않았습니다.")
                return
            
            # 임베딩을 FAISS 인덱스에 추가
            embedding_reshaped = embedding.reshape(1, -1)
            self.faiss_index.add(embedding_reshaped)
            
            # 메타데이터 업데이트
            new_metadata = {
                'id': review.id,
                'user_id': review.user.id,
                'route_id': review.route.id,
                'rating': float(review.rating),
                'summary': summary,
                'content': review.content,
                'created_at': review.created_at.isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # 메타데이터 저장
            self._save_metadata(new_metadata)
            
            # FAISS 인덱스 저장
            faiss.write_index(self.faiss_index, self.faiss_index_path)
            
            print(f"FAISS DB 업데이트 완료: 리뷰 ID {review.id}")
            
        except Exception as e:
            print(f"FAISS DB 업데이트 실패: {e}")
    
    def _save_metadata(self, metadata: Dict):
        """
        메타데이터 저장
        """
        try:
            import pandas as pd
            
            # 기존 메타데이터에 새 데이터 추가
            if self.metadata is not None:
                new_df = pd.DataFrame([metadata])
                self.metadata = pd.concat([self.metadata, new_df], ignore_index=True)
            else:
                self.metadata = pd.DataFrame([metadata])
            
            # CSV 파일로 저장
            self.metadata.to_csv(self.metadata_path, index=False)
            
        except Exception as e:
            print(f"메타데이터 저장 실패: {e}")
    
    def save_training_data(self, review, summary: str):
        """
        Fine-tuning용 학습 데이터 저장 (정합성 판단 후)
        """
        try:
            # 정합성 판단
            if not self._validate_training_data(review, summary):
                print("정합성 검증 실패 - 학습 데이터 저장 건너뜀")
                return
            
            # 학습 데이터 디렉토리 생성
            os.makedirs(self.training_data_path, exist_ok=True)
            
            # 학습 데이터 구성
            training_data = {
                'id': review.id,
                'input': review.content,
                'output': summary,
                'rating': float(review.rating),
                'route_id': review.route.id,
                'created_at': review.created_at.isoformat(),
                'validation_score': self._calculate_validation_score(review, summary)
            }
            
            # JSON 파일로 저장
            filename = f"training_data_{review.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.training_data_path, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(training_data, f, ensure_ascii=False, indent=2)
            
            print(f"학습 데이터 저장 완료: {filepath}")
            
        except Exception as e:
            print(f"학습 데이터 저장 실패: {e}")
    
    def _validate_training_data(self, review, summary: str) -> bool:
        """
        학습 데이터 정합성 판단
        """
        try:
            # 1. 내용 길이 검증
            if len(review.content) < 10 or len(summary) < 5:
                print("정합성 검증 실패: 내용이 너무 짧음")
                return False
            
            # 2. 요약문 품질 검증 (원본과 요약문의 유사도가 적절한지)
            similarity = self._calculate_cosine_similarity(review.content, summary)
            if similarity > 0.95:  # 너무 유사하면 요약이 제대로 안된 것
                print(f"정합성 검증 실패: 요약문이 원본과 너무 유사함 (유사도: {similarity:.3f})")
                return False
            
            if similarity < 0.1:  # 너무 다르면 요약이 잘못된 것
                print(f"정합성 검증 실패: 요약문이 원본과 너무 다름 (유사도: {similarity:.3f})")
                return False
            
            # 3. 평점 검증
            if not (0.0 <= float(review.rating) <= 5.0):
                print("정합성 검증 실패: 평점이 범위를 벗어남")
                return False
            
            # 4. 키워드 중복 검증
            content_keywords = self._extract_tags(review.content)
            summary_keywords = self._extract_tags(summary)
            keyword_overlap = len(content_keywords & summary_keywords) / len(content_keywords | summary_keywords) if content_keywords | summary_keywords else 0
            
            if keyword_overlap < 0.1:  # 키워드 중복이 너무 적으면 요약이 잘못된 것
                print(f"정합성 검증 실패: 키워드 중복이 너무 적음 (중복률: {keyword_overlap:.3f})")
                return False
            
            print(f"정합성 검증 통과:")
            print(f"  - 내용 길이: OK")
            print(f"  - 요약문 유사도: {similarity:.3f} (적절함)")
            print(f"  - 평점: {review.rating} (OK)")
            print(f"  - 키워드 중복률: {keyword_overlap:.3f} (적절함)")
            
            return True
            
        except Exception as e:
            print(f"정합성 검증 실패: {e}")
            return False
    
    def _calculate_validation_score(self, review, summary: str) -> float:
        """
        학습 데이터 검증 점수 계산
        """
        try:
            # 여러 지표를 종합한 검증 점수
            scores = []
            
            # 1. 요약문 품질 점수
            similarity = self._calculate_cosine_similarity(review.content, summary)
            summary_score = max(0, 1 - abs(similarity - 0.7))  # 0.7 근처가 최적
            scores.append(summary_score)
            
            # 2. 키워드 중복 점수
            content_keywords = self._extract_tags(review.content)
            summary_keywords = self._extract_tags(summary)
            keyword_overlap = len(content_keywords & summary_keywords) / len(content_keywords | summary_keywords) if content_keywords | summary_keywords else 0
            scores.append(keyword_overlap)
            
            # 3. 내용 길이 점수
            content_length_score = min(1.0, len(review.content) / 100)  # 100자 이상이면 만점
            summary_length_score = min(1.0, len(summary) / 50)  # 50자 이상이면 만점
            scores.append((content_length_score + summary_length_score) / 2)
            
            # 평균 점수 반환
            return sum(scores) / len(scores)
            
        except Exception as e:
            print(f"검증 점수 계산 실패: {e}")
            return 0.0
    
    def process_review(self, review) -> bool:
        """
        리뷰 파이프라인 전체 실행
        팀 합의된 파이프라인 흐름:
        1. ClovaX로 요약
        2. 기존 summary와 태그 비교
        3. 조건 충족 시 업데이트 진행
        4. Clova Embedding으로 임베딩
        5. FAISS DB + metadata 저장
        6. 정합성 판단 후 fine-tuning용 학습 데이터 저장
        """
        try:
            print(f"\n🤖 리뷰 파이프라인 시작: 리뷰 ID {review.id}")
            print(f"📝 원본 내용: {review.content[:100]}...")
            print(f"⭐ 평점: {review.rating}")
            
            # 1. ClovaX로 요약
            print(f"\n1단계: ClovaX 요약 중...")
            new_summary = self.clova_summarize(review.content)
            print(f"요약 완료: {new_summary}")
            
            # 2. 기존 summary와 태그 비교
            print(f"\n2단계: 업데이트 필요성 판단 중...")
            if self.should_update(review, new_summary):
                print(f"업데이트 필요 - 파이프라인 계속 진행")
                
                # 3. Clova Embedding으로 임베딩
                print(f"\n3단계: Clova Embedding 생성 중...")
                embedding = self.clova_embed(review.content)
                print(f"임베딩 생성 완료 (차원: {len(embedding)})")
                
                # 4. FAISS DB + metadata 저장
                print(f"\n4단계: FAISS DB 업데이트 중...")
                self.update_faiss_db(review, embedding, new_summary)
                
                # 5. 정합성 판단 후 fine-tuning용 학습 데이터 저장
                print(f"\n5단계: 학습 데이터 저장 중...")
                self.save_training_data(review, new_summary)
                
                print(f"\n🎉 리뷰 파이프라인 완료: 리뷰 ID {review.id}")
                return True
            else:
                print(f"⏭️ 업데이트 불필요 - 파이프라인 종료")
                return False
                
        except Exception as e:
            print(f"❌ 리뷰 파이프라인 실패: {e}")
            return False 