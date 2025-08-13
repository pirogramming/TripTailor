import json
from typing import List, Dict
from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder

from apps.places.services import VectorSearchService
from apps.places.models import Place
from apps.tags.models import Tag


class Command(BaseCommand):
    help = "pgvector 기반 벡터 검색 및 임베딩 업데이트"

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=['search', 'update-embeddings', 'test'],
            default='test',
            help='실행할 작업'
        )
        parser.add_argument(
            '--query',
            type=str,
            help='검색 쿼리 (search 액션에서 사용)'
        )
        parser.add_argument(
            '--tags',
            type=str,
            help='사용자 태그 (쉼표로 구분, search 액션에서 사용)'
        )
        parser.add_argument(
            '--region',
            type=str,
            help='지역 필터 (search 액션에서 사용)'
        )
        parser.add_argument(
            '--place-class',
            type=int,
            help='장소 카테고리 필터 (search 액션에서 사용)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='검색 결과 개수 제한'
        )
        parser.add_argument(
            '--place-ids',
            type=str,
            help='임베딩 업데이트할 장소 ID들 (쉼표로 구분)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='결과를 저장할 JSON 파일 경로'
        )

    def handle(self, *args, **options):
        service = VectorSearchService()
        
        action = options['action']
        
        if action == 'search':
            self._handle_search(service, options)
        elif action == 'update-embeddings':
            self._handle_update_embeddings(service, options)
        elif action == 'test':
            self._handle_test(service, options)
            
    def _handle_search(self, service: VectorSearchService, options: Dict):
        """검색 실행"""
        query = options.get('query')
        if not query:
            self.stderr.write("❌ 검색 쿼리가 필요합니다. --query 옵션을 사용하세요.")
            return
            
        # 태그 파싱
        user_tags = None
        if options.get('tags'):
            user_tags = [tag.strip() for tag in options['tags'].split(',')]
            
        # 검색 실행
        self.stdout.write(f"🔍 검색 시작: '{query}'")
        if user_tags:
            self.stdout.write(f"🏷️ 사용자 태그: {user_tags}")
            
        results = service.search_places(
            query=query,
            user_tags=user_tags,
            region=options.get('region'),
            place_class=options.get('place_class'),
            limit=options['limit']
        )
        
        # 결과 출력
        self._print_search_results(results)
        
        # JSON 파일로 저장
        if options.get('output'):
            self._save_results_to_json(results, options['output'])
            
    def _handle_update_embeddings(self, service: VectorSearchService, options: Dict):
        """임베딩 업데이트"""
        place_ids = None
        if options.get('place_ids'):
            place_ids = [int(pid.strip()) for pid in options['place_ids'].split(',')]
            
        self.stdout.write("🔄 임베딩 업데이트 시작...")
        
        if place_ids:
            self.stdout.write(f"📝 대상 장소 ID: {place_ids}")
        else:
            self.stdout.write("📝 전체 장소 대상")
            
        updated_count = service.update_place_embeddings(place_ids)
        
        self.stdout.write(f"✅ 임베딩 업데이트 완료: {updated_count}개 장소")
        
    def _handle_test(self, service: VectorSearchService, options: Dict):
        """테스트 검색 실행"""
        test_queries = [
            "서울에서 한강 뷰가 좋은 카페",
            "부산에서 맛있는 해산물",
            "제주도에서 힐링할 수 있는 곳",
            "대구에서 데이트하기 좋은 장소",
            "인천에서 쇼핑하기 좋은 곳"
        ]
        
        self.stdout.write("🧪 테스트 검색 시작...")
        
        for i, query in enumerate(test_queries, 1):
            self.stdout.write(f"\n{'='*50}")
            self.stdout.write(f"테스트 {i}: '{query}'")
            self.stdout.write(f"{'='*50}")
            
            results = service.search_places(
                query=query,
                limit=5
            )
            
            self._print_search_results(results, show_details=True)
            
    def _print_search_results(self, results: List[Dict], show_details: bool = False):
        """검색 결과 출력"""
        if not results:
            self.stdout.write("❌ 검색 결과가 없습니다.")
            return
            
        self.stdout.write(f"\n📊 검색 결과 ({len(results)}개):")
        self.stdout.write("-" * 80)
        
        for i, result in enumerate(results, 1):
            place = result['place']
            self.stdout.write(f"{i}. {place.name}")
            self.stdout.write(f"   📍 {place.address}")
            self.stdout.write(f"   🏷️ {', '.join(result['tags']) if result['tags'] else '태그 없음'}")
            
            if show_details:
                self.stdout.write(f"   📊 점수: {result['score']:.3f}")
                self.stdout.write(f"   🔢 코사인: {result['cosine_score']:.3f}")
                self.stdout.write(f"   🏷️ 태그: {result['tag_score']:.3f}")
                self.stdout.write(f"   ⭐ 인기도: {result['popularity_score']:.3f}")
                
            if place.overview:
                overview = place.overview[:100] + "..." if len(place.overview) > 100 else place.overview
                self.stdout.write(f"   📝 {overview}")
                
            self.stdout.write("")
            
    def _save_results_to_json(self, results: List[Dict], filepath: str):
        """결과를 JSON 파일로 저장"""
        try:
            # Place 객체를 직렬화 가능한 형태로 변환
            serializable_results = []
            for result in results:
                serializable_result = {
                    'id': result['place'].id,
                    'name': result['name'],
                    'address': result['address'],
                    'region': result['region'],
                    'overview': result['overview'],
                    'summary': result['summary'],
                    'lat': result['lat'],
                    'lng': result['lng'],
                    'place_class': result['place_class'],
                    'tags': result['tags'],
                    'score': result['score'],
                    'cosine_score': result['cosine_score'],
                    'tag_score': result['tag_score'],
                    'popularity_score': result['popularity_score']
                }
                serializable_results.append(serializable_result)
                
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder)
                
            self.stdout.write(f"💾 결과가 {filepath}에 저장되었습니다.")
            
        except Exception as e:
            self.stderr.write(f"❌ 결과 저장 실패: {e}")


# 사용 예시:
# python manage.py vector_search --action search --query "서울 카페" --limit 5
# python manage.py vector_search --action update-embeddings --place-ids "1,2,3"
# python manage.py vector_search --action test
