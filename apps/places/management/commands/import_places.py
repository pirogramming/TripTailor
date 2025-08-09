import csv
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.tags.models import Tag
from apps.places.models import Place
from decimal import Decimal

class Command(BaseCommand):
    help = 'CSV 파일에서 Place 데이터를 불러와 DB에 저장합니다.'

    def handle(self, *args, **options):
        csv_path = os.path.join(settings.BASE_DIR, 'triptailor_full_metadata.csv')
        with open(csv_path, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                name = row.get('명칭')
                address = row.get('주소')
                region = address.split()[0] if address else ''
                overview = row.get('개요')
                lat = row.get('위도') or row.get('lat')
                lng = row.get('경도') or row.get('lng')
                external_id = row.get('external_id', None)
                is_unique = row.get('is_unique', '0')
                summary = row.get('summary', '')
                place_class = int(row.get('class', '0'))

                if not (name and address and overview and region and lat and lng):
                    continue

                try:
                    lat = Decimal(lat)
                    lng = Decimal(lng)
                except Exception:
                    continue

                is_unique = str(is_unique).strip() in ['1', 'True', 'true']

                place, created = Place.objects.update_or_create(
                    name=name,
                    address=address,
                    defaults={
                        'region': region,
                        'lat': lat,
                        'lng': lng,
                        'overview': overview,
                        'external_id': external_id,
                        'is_unique': is_unique,
                        'summary': summary,
                        'place_class': place_class,  # 항상 class 값 업데이트
                    }
                )

                tag_str = row.get('tags', '')
                tag_names = [t.strip().lstrip('#') for t in tag_str.split() if t.strip()]
                for tag_name in tag_names:
                    tag, _ = Tag.objects.get_or_create(name=tag_name)
                    place.tags.add(tag)
                count += 1
        self.stdout.write(self.style.SUCCESS(f'{count}개 장소가 저장되었습니다.'))