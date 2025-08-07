import os
import json
import numpy as np
from typing import Dict, List, Optional, Tuple
import faiss
from datetime import datetime

class ReviewPipelineService:
    """
    리뷰 파이프라인 서비스
    - ClovaX로 요약
    - 기존 summary와 태그 비교
    - 조건 충족 시 임베딩 및 저장
    """
    
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
            # TODO: 실제 ClovaX API 호출
            # 현재는 간단한 요약 로직으로 대체
            if len(content) > 100:
                return content[:100] + "..."
            return content
        except Exception as e:
            print(f"ClovaX 요약 실패: {e}")
            return content[:50] if content else ""
    
    def clova_embed(self, content: str) -> np.ndarray:
        """
        Clova Embedding으로 임베딩 생성
        """
        try:
            # TODO: 실제 Clova Embedding API 호출
            # 현재는 더미 임베딩으로 대체
            embedding_dim = 768  # 일반적인 임베딩 차원
            return np.random.randn(embedding_dim).astype('float32')
        except Exception as e:
            print(f"Clova Embedding 실패: {e}")
            return np.zeros(768, dtype='float32')
    
    def should_update(self, review, new_summary: str) -> bool:
        """
        기존 summary와 비교하여 업데이트 필요 여부 판단
        """
        try:
            # 기존 summary와 새로운 summary 비교
            old_summary = review.summary
            
            # 간단한 유사도 계산 (실제로는 더 정교한 방법 사용)
            similarity = self._calculate_similarity(old_summary, new_summary)
            
            # 유사도가 낮으면 업데이트 필요
            return similarity < 0.7  # 임계값
            
        except Exception as e:
            print(f"업데이트 판단 실패: {e}")
            return True  # 오류 시 업데이트 진행
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        두 텍스트 간의 유사도 계산
        """
        try:
            # 간단한 Jaccard 유사도 계산
            words1 = set(text1.lower().split())
            words2 = set(text2.lower().split())
            
            if not words1 or not words2:
                return 0.0
            
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            
            return intersection / union if union > 0 else 0.0
            
        except Exception as e:
            print(f"유사도 계산 실패: {e}")
            return 0.0
    
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
        Fine-tuning용 학습 데이터 저장
        """
        try:
            # 학습 데이터 디렉토리 생성
            os.makedirs(self.training_data_path, exist_ok=True)
            
            # 학습 데이터 구성
            training_data = {
                'id': review.id,
                'input': review.content,
                'output': summary,
                'rating': float(review.rating),
                'route_id': review.route.id,
                'created_at': review.created_at.isoformat()
            }
            
            # JSON 파일로 저장
            filename = f"training_data_{review.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.training_data_path, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(training_data, f, ensure_ascii=False, indent=2)
            
            print(f"학습 데이터 저장 완료: {filepath}")
            
        except Exception as e:
            print(f"학습 데이터 저장 실패: {e}")
    
    def process_review(self, review) -> bool:
        """
        리뷰 파이프라인 전체 실행
        """
        try:
            print(f"리뷰 파이프라인 시작: 리뷰 ID {review.id}")
            
            # 1. ClovaX로 요약
            new_summary = self.clova_summarize(review.content)
            print(f"요약 완료: {new_summary[:50]}...")
            
            # 2. 기존 summary와 비교
            if self.should_update(review, new_summary):
                print("업데이트 필요 - 파이프라인 계속 진행")
                
                # 3. Clova Embedding으로 임베딩
                embedding = self.clova_embed(review.content)
                print("임베딩 생성 완료")
                
                # 4. FAISS DB + metadata 저장
                self.update_faiss_db(review, embedding, new_summary)
                
                # 5. Fine-tuning용 학습 데이터 저장
                self.save_training_data(review, new_summary)
                
                print(f"리뷰 파이프라인 완료: 리뷰 ID {review.id}")
                return True
            else:
                print("업데이트 불필요 - 파이프라인 종료")
                return False
                
        except Exception as e:
            print(f"리뷰 파이프라인 실패: {e}")
            return False 