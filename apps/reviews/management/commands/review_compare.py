import os
import json
import uuid
import numpy as np
from typing import Dict
from datetime import datetime
import requests
from decouple import config

from django.core.management.base import BaseCommand
from django.conf import settings


def _get_base_dir() -> str:
    return str(getattr(settings, "BASE_DIR", os.getcwd()))


class ReviewPipelineService:
    def __init__(self):
        base_dir = _get_base_dir()
        self.metadata_path = os.path.join(base_dir, "triptailor_full_metadata.csv")
        self.training_data_path = os.path.join(base_dir, "training_data")

        # 메타데이터 로드
        self.metadata = self._load_metadata()

    # ---------------------------
    # Loaders & Utilities
    # ---------------------------
    def _load_metadata(self):
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

    # ---------------------------
    # Clova: Summarize
    # ---------------------------
    def clova_summarize(self, content: str) -> str:
        """
        ClovaX(HCX-005)로 후기 요약. 키 없거나 실패 시 fallback.
        """
        try:
            api_key = config("CLOVASTUDIO_API_KEY", default=None)
            if not api_key:
                print("CLOVASTUDIO_API_KEY 미설정 → 더미 요약")
                return self._fallback_summarize(content)

            # LangChain 경유 (프로젝트에서 이미 사용 중)
            from langchain_naver import ChatClovaX
            from langchain_core.prompts import PromptTemplate

            if api_key:
                   os.environ["CLOVASTUDIO_API_KEY"] = api_key 

            llm = ChatClovaX(model="HCX-005", temperature=0 )
            prompt = PromptTemplate.from_template("다음 후기를 1~2문장으로 간결 요약:\n{review}")
            out = (prompt | llm).invoke({"review": content})
            text = getattr(out, "content", str(out)).strip()
            return text or self._fallback_summarize(content)
        except Exception as e:
            print(f"ClovaX 요약 실패: {e}")
            return self._fallback_summarize(content)

    def _fallback_summarize(self, content: str) -> str:
        return (content[:100] + "...") if len(content) > 100 else content



    # ---------------------------
    # Update Decision
    # ---------------------------
    def should_update(self, review, new_summary: str) -> bool:
        """
        업데이트 기준:
        - 요약문 cosine similarity < 0.9
        - 태그 집합 변화
        """
        try:
            old_summary = getattr(review, "summary", "") or ""
            summary_similarity = self._calculate_cosine_similarity(old_summary, new_summary)

            old_tags = self._extract_tags(old_summary)
            new_tags = self._extract_tags(new_summary)
            tags_different = old_tags != new_tags

            should_update = (summary_similarity < 0.9) or tags_different

            print("업데이트 판단:")
            print(f"  - 요약문 유사도: {summary_similarity:.3f} (임계값: 0.9)")
            print(f"  - 태그 다름: {tags_different}")
            print(f"  - 업데이트 필요: {should_update}")
            return should_update
        except Exception as e:
            print(f"업데이트 판단 실패: {e}")
            return True  # 보수적으로 진행

    def _calculate_cosine_similarity(self, text1: str, text2: str) -> float:
        try:
            words1 = (text1 or "").lower().split()
            words2 = (text2 or "").lower().split()
            from collections import Counter
            freq1, freq2 = Counter(words1), Counter(words2)
            vocab = set(freq1) | set(freq2)
            if not vocab:
                return 1.0
            v1 = [freq1.get(w, 0) for w in vocab]
            v2 = [freq2.get(w, 0) for w in vocab]
            dot = sum(a * b for a, b in zip(v1, v2))
            n1 = sum(a * a for a in v1) ** 0.5
            n2 = sum(b * b for b in v2) ** 0.5
            if n1 == 0 or n2 == 0:
                return 0.0
            return dot / (n1 * n2)
        except Exception:
            return 0.0

    def _extract_tags(self, text: str) -> set:
        try:
            import re
            stop = {
                'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
                'is','are','was','were','be','been','being','have','has','had','do','does',
                'did','will','would','could','should','may','might','must','can','this','that',
                'these','those','i','you','he','she','it','we','they','me','him','her','us',
                'them','my','your','his','its','our','their','mine','yours','hers','ours','theirs'
            }
            clean = re.sub(r"[^\w\s]", "", (text or "").lower())
            words = [w for w in clean.split() if w not in stop and len(w) > 2]
            from collections import Counter
            return {w for w, _ in Counter(words).most_common(5)}
        except Exception:
            return set()

    # ---------------------------
    # Database Update
    # ---------------------------
    def update_review_db(self, review, summary: str):
        """
        리뷰의 summary 필드를 DB에 업데이트
        """
        try:
            # Django 모델 import
            from apps.reviews.models import Review as ReviewModel
            
            # 리뷰 객체가 이미 Django 모델인 경우
            if hasattr(review, '_meta') and review._meta.model_name == 'review':
                review.summary = summary
                review.save(update_fields=['summary'])
                print(f"DB 업데이트 완료: 리뷰 ID {review.id}")
            else:
                # 리뷰 ID로 DB에서 조회하여 업데이트
                review_id = getattr(review, "id", None)
                if review_id:
                    try:
                        db_review = ReviewModel.objects.get(id=review_id)
                        db_review.summary = summary
                        db_review.save(update_fields=['summary'])
                        print(f"DB 업데이트 완료: 리뷰 ID {review_id}")
                    except ReviewModel.DoesNotExist:
                        print(f"DB에서 리뷰를 찾을 수 없음: ID {review_id}")
                else:
                    print("리뷰 ID가 없어 DB 업데이트 불가")
                    
        except Exception as e:
            print(f"DB 업데이트 실패: {e}")

    def _save_metadata(self, metadata: Dict):
        """
        메타데이터 저장 (기존 호환성을 위해 유지)
        """
        try:
            import pandas as pd
            if self.metadata is not None:
                self.metadata = pd.concat([self.metadata, pd.DataFrame([metadata])], ignore_index=True)
            else:
                self.metadata = pd.DataFrame([metadata])
            self.metadata.to_csv(self.metadata_path, index=False)
        except Exception as e:
            print(f"메타데이터 저장 실패: {e}")

    def save_training_data(self, review, summary: str):
        try:
            if not self._validate_training_data(review, summary):
                print("정합성 검증 실패 - 학습 데이터 저장 생략")
                return

            os.makedirs(self.training_data_path, exist_ok=True)
            training = {
                "id": getattr(review, "id", None),
                "input": getattr(review, "content", ""),
                "output": summary,
                "rating": float(getattr(review, "rating", 0.0) or 0.0),
                "route_id": getattr(getattr(review, "route", None), "id", None),
                "user_id": getattr(getattr(review, "user", None), "id", None),
                "created_at": getattr(review, "created_at", datetime.now()).isoformat(),
                "validation_score": self._calculate_validation_score(review, summary),
            }
            filename = f"training_data_{training['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.training_data_path, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(training, f, ensure_ascii=False, indent=2)
            print(f"학습 데이터 저장 완료: {filepath}")
        except Exception as e:
            print(f"학습 데이터 저장 실패: {e}")

    def _validate_training_data(self, review, summary: str) -> bool:
        try:
            content = getattr(review, "content", "") or ""
            if len(content) < 10 or len(summary) < 5:
                print("정합성 검증 실패: 내용이 너무 짧음")
                return False
            sim = self._calculate_cosine_similarity(content, summary)
            if sim > 0.95:
                print(f"정합성 검증 실패: 요약이 원문과 과도하게 유사 (유사도 {sim:.3f})")
                return False
            if sim < 0.1:
                print(f"정합성 검증 실패: 요약이 원문과 과도하게 상이 (유사도 {sim:.3f})")
                return False
            rating = float(getattr(review, "rating", 0.0) or 0.0)
            if not (0.0 <= rating <= 5.0):
                print("정합성 검증 실패: 평점 범위 오류")
                return False
            content_kw = self._extract_tags(content)
            summary_kw = self._extract_tags(summary)
            overlap = (len(content_kw & summary_kw) / len(content_kw | summary_kw)) if (content_kw | summary_kw) else 0
            if overlap < 0.1:
                print(f"정합성 검증 실패: 키워드 중복률 낮음 ({overlap:.3f})")
                return False

            print("정합성 검증 통과:")
            print(f"  - 요약 유사도: {sim:.3f}")
            print(f"  - 평점: {rating}")
            print(f"  - 키워드 중복률: {overlap:.3f}")
            return True
        except Exception as e:
            print(f"정합성 검증 실패: {e}")
            return False

    def _calculate_validation_score(self, review, summary: str) -> float:
        try:
            content = getattr(review, "content", "") or ""
            sim = self._calculate_cosine_similarity(content, summary)
            score1 = max(0, 1 - abs(sim - 0.7))  # 0.7 근처 최적
            kw_c = self._extract_tags(content)
            kw_s = self._extract_tags(summary)
            overlap = (len(kw_c & kw_s) / len(kw_c | kw_s)) if (kw_c | kw_s) else 0
            score2 = overlap
            score3 = (min(1.0, len(content) / 100) + min(1.0, len(summary) / 50)) / 2
            return (score1 + score2 + score3) / 3
        except Exception:
            return 0.0

    # ---------------------------
    # Orchestrator
    # ---------------------------
    def process_review(self, review) -> bool:
        """
        1) 요약 → 2) 기존 summary/태그와 비교 → 3) 필요 시 DB 업데이트 →
        4) 학습데이터 저장
        """
        try:
            print(f"\n🤖 리뷰 파이프라인 시작: 리뷰 ID {getattr(review, 'id', None)}")
            print(f"📝 원본 내용: {getattr(review, 'content', '')[:100]}...")
            print(f"⭐ 평점: {getattr(review, 'rating', None)}")

            print("\n1단계: ClovaX 요약 중...")
            new_summary = self.clova_summarize(getattr(review, "content", "") or "")
            print(f"요약 완료: {new_summary}")

            print("\n2단계: 업데이트 필요성 판단 중...")
            if self.should_update(review, new_summary):
                print("업데이트 필요 - 파이프라인 진행")

                print("\n3단계: DB 업데이트 중...")
                self.update_review_db(review, new_summary)

                print("\n5단계: 학습 데이터 저장 중...")
                self.save_training_data(review, new_summary)

                print(f"\n🎉 리뷰 파이프라인 완료: 리뷰 ID {getattr(review, 'id', None)}")
                return True
            else:
                print("⏭️ 업데이트 불필요 - 파이프라인 종료")
                return False
        except Exception as e:
            print(f"❌ 리뷰 파이프라인 실패: {e}")
            return False


# ============================
# Django Management Command
# ============================
class Command(BaseCommand):
    help = "TripTailor 리뷰 비교/DB 업데이트 파이프라인 실행"

    def add_arguments(self, parser):
        parser.add_argument("--review-id", type=int, help="특정 Review.id만 처리")
        parser.add_argument("--limit", type=int, help="전체 실행 시 개수 제한")
        parser.add_argument("--dummy", action="store_true", help="DB 없이 더미 실행")

    def _import_review_model(self):
        # 앱 경로 유연 지원: apps.reviews.models → 실패 시 reviews.models
        try:
            from apps.reviews.models import Review as _Review
            return _Review
        except Exception:
            from reviews.models import Review as _Review
            return _Review

    def handle(self, *args, **options):
        svc = ReviewPipelineService()

        if options.get("dummy"):
            self.stdout.write("더미 모드 실행")
            class DummyUser:
                def __init__(self, id): self.id = id
            class DummyRoute:
                def __init__(self, id): self.id = id
            class DummyReview:
                def __init__(self):
                    self.id = 999
                    self.user = DummyUser(1)
                    self.route = DummyRoute(None)
                    self.rating = 4.5
                    self.content = "시설이 깨끗하고 조용해서 힐링하기 좋은 곳이었어요."
                    self.summary = "시설이 깨끗하고 조용함"
                    self.created_at = datetime.now()
            review = DummyReview()
            svc.process_review(review)
            return

        Review = self._import_review_model()

        # 특정 리뷰 1건
        if options.get("review_id"):
            rid = options["review_id"]
            try:
                review = Review.objects.get(id=rid)
            except Review.DoesNotExist:
                self.stderr.write(f"❌ 리뷰 {rid} 없음")
                return
            svc.process_review(review)
            return

        # 전체 실행 (기본)
        qs = Review.objects.all().order_by("-id")
        limit = options.get("limit")
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"🔎 총 {total}개 리뷰 처리 시작…")
        fail = 0
        for i, review in enumerate(qs, start=1):
            self.stdout.write(f"\n---- [{i}/{total}] Review ID={review.id} ----")
            ok = svc.process_review(review)
            if not ok:
                fail += 1
        self.stdout.write(f"\n✅ 전체 처리 완료: 성공 {total - fail} / 실패 {fail}")
