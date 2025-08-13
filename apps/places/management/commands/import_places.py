import os
import csv
import re
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.tags.models import Tag
from apps.places.models import Place

# (선택) FAISS 사용
try:
    import faiss
    FAISS_AVAILABLE = True
except Exception:
    FAISS_AVAILABLE = False

def norm(s: str) -> str:
    s = s or ""
    return re.sub(r"[\s\(\)\[\]\-_/·•~!@#$%^&*=+|:;\"'<>?,.]+", "", s).lower()

class Command(BaseCommand):
    help = "CSV(필수) + (선택) FAISS index에서 Place 및 임베딩을 서버 DB에 적재합니다."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=False, help="CSV 경로 (기본: BASE_DIR/triptailor_full_metadata.csv)")
        parser.add_argument("--faiss", required=False, help="FAISS .index 경로 (벡터 저장 시)")
        parser.add_argument("--batch", type=int, default=500, help="태그 배치 커밋 간격")

    def handle(self, *args, **opts):
        csv_path = opts["csv"] or os.path.join(settings.BASE_DIR, "triptailor_full_metadata.csv")
        faiss_path = opts.get("faiss")
        batch_size = opts["batch"]

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV not found: {csv_path}")

        # 1) (선택) FAISS에서 벡터 복원
        vecs = None
        if faiss_path:
            if not FAISS_AVAILABLE:
                self.stderr.write(self.style.WARNING("faiss 모듈이 없어 임베딩은 건너뜁니다. (pip install faiss-cpu)"))
            elif not os.path.exists(faiss_path):
                self.stderr.write(self.style.WARNING(f"FAISS index가 없어서 임베딩은 건너뜁니다: {faiss_path}"))
            else:
                self.stdout.write(self.style.MIGRATE_HEADING("Load FAISS index"))
                index = faiss.read_index(faiss_path)
                n = index.ntotal
                self.stdout.write(f"- index.ntotal: {n}")
                try:
                    vecs = index.reconstruct_n(0, n)  # (n, dim) float32
                except Exception as e:
                    self.stderr.write(self.style.WARNING(
                        f"reconstruct_n 실패 → 임베딩 저장 건너뜀 (원본 임베딩 파일 필요). err={e}"
                    ))
                    vecs = None

        # 2) CSV 적재
        self.stdout.write(self.style.MIGRATE_HEADING("Load CSV & upsert"))
        count = 0

        # 태그 캐시(성능)
        tag_cache = {t.name: t.id for t in Tag.objects.all().only("id", "name")}
        new_tags = []

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = row.get("명칭")
                address = row.get("주소")
                overview = row.get("개요")
                lat = row.get("위도") or row.get("lat")
                lng = row.get("경도") or row.get("lng")
                summary = row.get("summary", "")
                external_id = row.get("external_id", None)
                is_unique = str(row.get("is_unique", "0")).strip() in ["1", "True", "true"]
                raw_cls = row.get("class", "0")
                try:
                    place_class = int(float(str(raw_cls).replace(",", ".").strip() or 0))
                except ValueError:
                    place_class = 0

                if not (name and address and overview and lat and lng):
                    continue

                try:
                    lat = Decimal(lat)
                    lng = Decimal(lng)
                except Exception:
                    continue

                region = address.split()[0] if address else ""

                # (선택) 임베딩
                embedding = None
                if vecs is not None and i < len(vecs):
                    embedding = vecs[i].astype("float32").tolist()

                # upsert
                place, _created = Place.objects.update_or_create(
                    name=name,
                    address=address,
                    defaults={
                        "region": region,
                        "lat": lat,
                        "lng": lng,
                        "overview": overview,
                        "external_id": external_id,
                        "is_unique": is_unique,
                        "summary": summary,
                        "place_class": place_class,
                        **({"embedding": embedding} if embedding is not None else {}),
                    },
                )

                # 태그 처리
                tag_str = row.get("tags", "")
                tag_names = [t.strip().lstrip("#") for t in tag_str.split() if t.strip()]

                tag_ids = []
                for tname in tag_names:
                    tid = tag_cache.get(tname)
                    if tid:
                        tag_ids.append(tid)
                    else:
                        new_tags.append(tname)

                # 새 태그 생성을 모아서 처리 (DB round-trip 절감)
                if len(new_tags) >= batch_size:
                    with transaction.atomic():
                        for nt in new_tags:
                            obj, _ = Tag.objects.get_or_create(name=nt)
                            tag_cache[obj.name] = obj.id
                    new_tags.clear()

                # place.tags.set/add
                if tag_names:
                    ids = [tag_cache[t] for t in tag_names if t in tag_cache]
                    if ids:
                        place.tags.add(*ids)

                count += 1

        # 남은 새 태그 처리
        if new_tags:
            with transaction.atomic():
                for nt in new_tags:
                    obj, _ = Tag.objects.get_or_create(name=nt)
                    tag_cache[obj.name] = obj.id

        self.stdout.write(self.style.SUCCESS(f"{count}개 장소가 저장되었습니다."))

        # 인덱스 안내
        if vecs is not None:
            self.stdout.write(self.style.HTTP_INFO(
                "임베딩 인덱스가 없다면 psql에서 생성:\n"
                "CREATE INDEX IF NOT EXISTS place_embedding_ivfflat "
                "ON places_place USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);\n"
                "ANALYZE places_place;"
            ))
