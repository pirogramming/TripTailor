import os
from datetime import datetime
from decouple import config

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction





class PlaceReviewProcessor:
    """
    장소별 댓글(리뷰) 집계 및 AI 요약을 통한 태그 업데이트 처리
    새로운 댓글이 추가될 때마다 해당 장소의 모든 댓글들을 종합 요약하고 태그 업데이트
    """
    
    def __init__(self):
        pass
    
    def get_place_all_reviews(self, place_id: int):
        """특정 장소의 모든 댓글 수집"""
        try:
            from apps.reviews.models import Review
            from apps.places.models import Place
            
            place = Place.objects.get(id=place_id)
            reviews = Review.objects.filter(place=place).select_related('user').order_by('-created_at')
            
            print(f"📍 장소 '{place.name}'의 댓글 {reviews.count()}개 수집")
            return place, reviews
        except Exception as e:
            print(f"❌ 장소 댓글 수집 실패: {e}")
            return None, None

    def summarize_all_place_reviews(self, reviews, target_length=(200, 700)) -> str:
        """
        장소의 모든 댓글을 ClovaX로 종합하여 200-700자 범위로 요약
        """
        try:
            if not reviews.exists():
                return "댓글이 없습니다."
            
            # 모든 댓글 내용 결합
            all_content = []
            for review in reviews:
                content = getattr(review, 'content', '') or ''
                rating = getattr(review, 'rating', 0)
                if content:
                    all_content.append(f"[평점: {rating}] {content}")
            
            if not all_content:
                return "유효한 댓글 내용이 없습니다."
            
            combined_content = "\n".join(all_content)
            print(f"📝 총 {len(all_content)}개 댓글을 종합하여 요약 진행...")
            
            # ClovaX로 종합 요약 (목표 길이 명시)
            api_key = config("CLOVASTUDIO_API_KEY", default=None)
            if not api_key:
                print("CLOVASTUDIO_API_KEY 미설정 → 기본 요약 사용")
                return self._fallback_place_summarize(combined_content, target_length)

            from langchain_naver import ChatClovaX
            from langchain_core.prompts import PromptTemplate

            os.environ["CLOVASTUDIO_API_KEY"] = api_key 
            llm = ChatClovaX(model="HCX-005", temperature=0.1)
            
            prompt = PromptTemplate.from_template(
                """다음은 한 장소에 대한 여러 방문객들의 댓글입니다. 
이 댓글들을 종합 분석하여 {min_length}-{max_length}자 사이로 요약해주세요.

요약에 포함할 내용:
- 장소의 주요 특징과 분위기
- 시설 및 서비스 품질
- 방문객들의 전반적인 만족도
- 자주 언급되는 긍정적/부정적 요소
- 추천 포인트나 주의사항

댓글 내용:
{reviews}

종합 요약:"""
            )
            
            out = (prompt | llm).invoke({
                "reviews": combined_content[:4000],  # 토큰 제한 고려
                "min_length": target_length[0],
                "max_length": target_length[1]
            })
            
            summary = getattr(out, "content", str(out)).strip()
            
            # 길이 체크 및 조정
            if len(summary) < target_length[0]:
                print(f"⚠️ 요약이 너무 짧음 ({len(summary)}자) - 확장 시도")
                summary = self._expand_summary(summary, combined_content, target_length)
            elif len(summary) > target_length[1]:
                print(f"⚠️ 요약이 너무 김 ({len(summary)}자) - 단축")
                summary = summary[:target_length[1]-3] + "..."
            
            print(f"✅ ClovaX 요약 완료 ({len(summary)}자)")
            return summary
            
        except Exception as e:
            print(f"❌ ClovaX 장소 댓글 요약 실패: {e}")
            return self._fallback_place_summarize(combined_content if 'combined_content' in locals() else "", target_length)
    
    def _fallback_place_summarize(self, content: str, target_length=(200, 700)) -> str:
        """ClovaX 요약 실패 시 대체 요약"""
        if not content:
            return "댓글 내용이 없습니다."
        
        print("💡 기본 요약 방식 사용")
        
        # 간단한 텍스트 요약 (키워드 기반)
        sentences = content.split('.')
        important_sentences = []
        
        # 장소 관련 중요 키워드
        keywords = ['좋', '맛있', '깨끗', '친절', '편리', '추천', '만족', '분위기', '시설', 
                   '서비스', '직원', '음식', '가격', '위치', '주차', '넓', '조용', '예쁜']
        
        for sentence in sentences[:15]:  # 최대 15문장 처리
            if any(keyword in sentence for keyword in keywords) and len(sentence.strip()) > 10:
                important_sentences.append(sentence.strip())
            if len(' '.join(important_sentences)) > target_length[0]:
                break
        
        summary = ' '.join(important_sentences)
        if len(summary) > target_length[1]:
            summary = summary[:target_length[1]-3] + "..."
        
        return summary or content[:target_length[1]]
    
    def _expand_summary(self, short_summary: str, original_content: str, target_length: tuple) -> str:
        """짧은 요약을 확장"""
        try:
            # 원본에서 추가 정보 추출
            additional_sentences = original_content.split('.')[:5]
            additional_info = '. '.join([s.strip() for s in additional_sentences if len(s.strip()) > 10])
            
            if additional_info:
                expanded = f"{short_summary} {additional_info}"
            else:
                expanded = short_summary
            
            if len(expanded) > target_length[1]:
                expanded = expanded[:target_length[1]-3] + "..."
            
            return expanded
        except:
            return short_summary
    
    def extract_place_tags_from_summary(self, summary: str) -> set:
        """
        요약에서 장소 특성에 맞는 태그를 추출
        """
        try:
            # 장소 관련 키워드 매핑
            place_keywords = {
                '깨끗함': ['깨끗', '청결', '위생적', '정리'],
                '맛있음': ['맛있', '맛집', '음식', '요리', '메뉴'], 
                '친절함': ['친절', '서비스', '직원', '응대'],
                '조용함': ['조용', '평화', '힐링', '휴식', '차분'],
                '좋은분위기': ['분위기', '인테리어', '예쁜', '아늑', '멋진'],
                '편리함': ['편리', '접근성', '교통', '주차', '위치'],
                '넓음': ['넓', '공간', '규모', '크'],
                '좋은경치': ['경치', '뷰', '전망', '풍경', '바다', '산'],
                '가족친화': ['가족', '아이', '어린이', '패밀리', '아기'],
                '데이트': ['데이트', '커플', '연인', '로맨틱'],
                '체험활동': ['체험', '활동', '프로그램', '이벤트'],
                '전통적': ['전통', '역사', '문화', '유적', '고전'],
                '현대적': ['모던', '세련', '신식', '최신'],
                '자연친화': ['자연', '공원', '숲', '녹지'],
                '쇼핑': ['쇼핑', '매장', '상품', '구매', '판매'],
                '레포츠': ['운동', '스포츠', '액티비티', '레저']
            }
            
            extracted_tags = set()
            summary_lower = summary.lower()
            
            # 키워드 기반 태그 추출
            for main_tag, related_words in place_keywords.items():
                if any(word in summary_lower for word in related_words):
                    extracted_tags.add(main_tag)
            
            # 추가로 빈도수 기반 키워드 추출
            import re
            from collections import Counter
            
            # 불용어 제거
            stop_words = {
                '이', '그', '저', '것', '수', '있', '없', '등', '및', '또', '더', '가장', '많', '정말',
                '매우', '너무', '아주', '정말', '진짜', '완전', '엄청', '여기', '거기', '저기'
            }
            
            clean_text = re.sub(r"[^\w\s]", "", summary_lower)
            words = [w for w in clean_text.split() if w not in stop_words and len(w) > 1]
            
            # 빈도수 높은 단어 중 의미있는 것들 추가
            frequent_words = Counter(words).most_common(8)
            for word, count in frequent_words:
                if count >= 2 and len(word) > 2:  # 2회 이상 등장하는 3글자 이상 단어
                    extracted_tags.add(word)
            
            return extracted_tags
                    
        except Exception as e:
            print(f"❌ 태그 추출 실패: {e}")
            return set()

    def compare_and_update_place_tags(self, place, summary: str) -> bool:
        """
        요약 내용과 현재 장소 태그를 비교하여 맞지 않는 경우 태그 업데이트
        """
        try:
            from apps.tags.models import Tag
            
            # 현재 장소의 태그들
            current_tags = set(place.tags.values_list('name', flat=True))
            print(f"📋 현재 장소 태그: {current_tags}")
            
            # 요약에서 추출한 새로운 태그들
            extracted_tags = self.extract_place_tags_from_summary(summary)
            print(f"🔍 요약에서 추출된 태그: {extracted_tags}")
            
            # 새로 추가할 태그들 (기존에 없는 것들)
            new_tags = extracted_tags - current_tags
            
            # 태그 업데이트가 필요한 경우
            if new_tags:
                print(f"➕ 새로 추가할 태그: {new_tags}")
                
                with transaction.atomic():
                    for tag_name in new_tags:
                        # 태그가 존재하지 않으면 생성, 있으면 가져오기
                        tag, created = Tag.objects.get_or_create(
                            name=tag_name,
                            defaults={'tag_type': 'ai_generated'}
                        )
                        place.tags.add(tag)
                        
                        if created:
                            print(f"   🆕 새 태그 생성 및 추가: {tag_name}")
                        else:
                            print(f"   ✅ 기존 태그 추가: {tag_name}")
                
                place.save()
                print(f"🏷️ 장소 '{place.name}' 태그 업데이트 완료")
                return True
            else:
                print("⏭️ 추가할 새 태그 없음 - 기존 태그와 일치")
                return False

        except Exception as e:
            print(f"❌ 태그 업데이트 실패: {e}")
            return False

    def process_place_when_review_added(self, place_id: int) -> bool:
        """
        새로운 댓글이 추가될 때마다 실행되는 메인 처리 함수
        1) 해당 장소의 모든 댓글 수집
        2) AI 요약 (200-700자)  
        3) 태그 비교 및 업데이트
        """
        try:
            print(f"\n🔄 댓글 추가로 인한 장소 분석 시작: Place ID {place_id}")
            
            # 1단계: 장소의 모든 리뷰 수집
            place, reviews = self.get_place_all_reviews(place_id)
            if not place:
                print("❌ 장소를 찾을 수 없습니다.")
                return False
                
            if not reviews.exists():
                print("❌ 처리할 댓글이 없습니다.")
                return False
            
            print(f"📊 총 {reviews.count()}개의 댓글 발견")
            
            # 2단계: ClovaX를 통한 종합 요약 (200-700자)
            print("\n🤖 ClovaX로 댓글 종합 요약 중...")
            summary = self.summarize_all_place_reviews(reviews)
            print(f"📝 요약 결과 ({len(summary)}자): {summary[:100]}...")
            
            # 3단계: 태그 분석 및 업데이트
            print("\n🏷️ 요약 기반 태그 분석 및 업데이트...")
            tag_updated = self.compare_and_update_place_tags(place, summary)
            
            # 4단계: 장소 summary 필드도 업데이트 (선택사항)
            if hasattr(place, 'summary'):
                place.summary = summary
                place.save(update_fields=['summary'])
                print("💾 장소 요약 필드 업데이트 완료")
            
            print(f"\n🎉 장소 '{place.name}' 댓글 기반 분석 완료!")
            print(f"   - 요약 길이: {len(summary)}자")
            print(f"   - 태그 업데이트: {'✅' if tag_updated else '⏭️ 변경없음'}")
            
            return True
            
        except Exception as e:
            print(f"❌ 장소 댓글 분석 실패: {e}")
            import traceback
            traceback.print_exc()
            return False


# ============================
# Django Management Command
# ============================
class Command(BaseCommand):
    help = """TripTailor 장소별 댓글 종합 분석 및 태그 업데이트

사용법:
  python manage.py review_compare --place-id 1       # 특정 장소의 모든 댓글 종합 분석
  python manage.py review_compare --all-places       # 모든 장소의 댓글 종합 분석
  python manage.py review_compare --place-id 1 --summary-min 300 --summary-max 500  # 요약 길이 조정

기능:
- 장소별 모든 댓글을 ClovaX로 200-700자 종합 요약
- 요약 내용 기반으로 장소 태그 자동 업데이트
- 댓글 추가 시마다 실행 가능한 구조
"""

    def add_arguments(self, parser):
        # 장소별 댓글 종합 처리
        parser.add_argument("--place-id", type=int, help="특정 Place.id의 모든 댓글을 종합 분석")
        parser.add_argument("--all-places", action="store_true", help="모든 장소의 댓글을 종합 분석")
        parser.add_argument("--min-reviews", type=int, default=3, help="분석할 최소 댓글 수 (기본: 3개)")
        parser.add_argument("--summary-min", type=int, default=200, help="AI 요약 최소 길이 (기본: 200자)")
        parser.add_argument("--summary-max", type=int, default=700, help="AI 요약 최대 길이 (기본: 700자)")
        parser.add_argument("--force-update", action="store_true", help="기존 태그와 상관없이 강제 업데이트")

    def handle(self, *args, **options):
        # 장소별 댓글 종합 처리만 지원
        if not (options.get("place_id") or options.get("all_places")):
            self.stderr.write("❌ --place-id 또는 --all-places 옵션이 필요합니다.")
            self.stderr.write("도움말: python manage.py review_compare --help")
            return

        self._handle_place_reviews(options)
    
    def _handle_place_reviews(self, options):
        """
        장소별 댓글 종합 처리 핸들러
        """
        place_processor = PlaceReviewProcessor()
        
        min_reviews = options.get("min_reviews", 3)
        summary_length = (
            options.get("summary_min", 200),
            options.get("summary_max", 700)
        )
        
        try:
            from django.db import models
            from apps.places.models import Place
            from apps.reviews.models import Review
            
            # 특정 장소 처리
            if options.get("place_id"):
                place_id = options["place_id"]
                self.stdout.write(f"\n🏢 특정 장소 댓글 종합 분석: Place ID {place_id}")
                
                try:
                    place = Place.objects.get(id=place_id)
                    review_count = Review.objects.filter(place=place).count()
                    
                    if review_count < min_reviews:
                        self.stdout.write(
                            f"⚠️ 장소 '{place.name}' 댓글 수({review_count})가 "
                            f"최소 요구 수({min_reviews})보다 적음"
                        )
                        self.stdout.write("그래도 처리를 진행합니다...")
                    
                    self.stdout.write(f"📍 장소: {place.name} (댓글 {review_count}개)")
                    self.stdout.write(f"📏 요약 길이: {summary_length[0]}-{summary_length[1]}자")
                    
                    # 커스텀 길이로 처리하기 위해 메서드 수정
                    success = self._process_single_place_with_custom_length(
                        place_processor, place_id, summary_length
                    )
                    
                    if success:
                        self.stdout.write(f"✅ 장소 '{place.name}' 댓글 종합 분석 완료!")
                    else:
                        self.stderr.write(f"❌ 장소 '{place.name}' 처리 실패")
                        
                except Place.DoesNotExist:
                    self.stderr.write(f"❌ 장소 ID {place_id}를 찾을 수 없음")
                return
            
            # 모든 장소 처리
            if options.get("all_places"):
                self.stdout.write("\n🏢 모든 장소 댓글 종합 분석 시작")
                
                # 댓글이 있는 장소들만 조회 (최소 댓글 수 이상)
                places_with_reviews = Place.objects.filter(
                    reviews__isnull=False
                ).annotate(
                    review_count=models.Count('reviews')
                ).filter(
                    review_count__gte=min_reviews
                ).distinct().order_by('-review_count')
                
                total_places = places_with_reviews.count()
                self.stdout.write(f"📊 처리 대상: {total_places}개 장소 (최소 댓글 {min_reviews}개 이상)")
                self.stdout.write(f"📏 요약 길이: {summary_length[0]}-{summary_length[1]}자")
                
                if total_places == 0:
                    self.stdout.write("⚠️ 처리할 장소가 없습니다.")
                    return

                success_count = 0
                fail_count = 0
                
                for i, place in enumerate(places_with_reviews, start=1):
                    self.stdout.write(f"\n[{i}/{total_places}] 📍 {place.name} (댓글 {place.review_count}개)")
                    
                    try:
                        success = self._process_single_place_with_custom_length(
                            place_processor, place.id, summary_length
                        )
                        
                        if success:
                            success_count += 1
                            self.stdout.write("   ✅ 완료")
                        else:
                            fail_count += 1
                            self.stdout.write("   ❌ 실패")
                            
                    except Exception as e:
                        self.stderr.write(f"   ❌ 오류 발생: {e}")
                        fail_count += 1
                
                self.stdout.write(f"\n🎉 전체 장소 댓글 분석 완료!")
                self.stdout.write(f"   📈 성공: {success_count}개")
                self.stdout.write(f"   📉 실패: {fail_count}개")
                
        except Exception as e:
            self.stderr.write(f"❌ 장소별 댓글 처리 중 치명적 오류: {e}")
            import traceback
            traceback.print_exc()
    
    def _process_single_place_with_custom_length(self, processor, place_id, target_length):
        """
        특정 장소를 커스텀 요약 길이로 처리
        """
        try:
            # 1단계: 장소와 댓글들 수집
            place, reviews = processor.get_place_all_reviews(place_id)
            if not place or not reviews.exists():
                return False
            
            # 2단계: 커스텀 길이로 요약
            summary = processor.summarize_all_place_reviews(reviews, target_length)
            
            # 3단계: 태그 비교 및 업데이트
            tag_updated = processor.compare_and_update_place_tags(place, summary)
            
            # 4단계: 장소 summary 필드 업데이트
            if hasattr(place, 'summary'):
                place.summary = summary
                place.save(update_fields=['summary'])
            
            return True
            
        except Exception as e:
            print(f"❌ 장소 처리 실패: {e}")
            return False
