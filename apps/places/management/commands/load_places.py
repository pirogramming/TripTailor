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
        parser.add_argument("--csv", required=False,
                            help="CSV 경로 (기본: /app/data/triptailor_full_metadata.csv → 없으면 BASE_DIR/triptailor_full_metadata.csv)")
        parser.add_argument("--faiss", required=False, help="FAISS .index 경로 (벡터 저장 시)")
        parser.add_argument("--batch", type=int, default=500, help="태그/로그/부분커밋 간격")
        parser.add_argument("--no-embedding", action="store_true",
                            help="임베딩 저장 건너뜀 (FAISS 없이 CSV만 적재)")
        parser.add_argument("--dim", type=int, default=None,
                            help="벡터 차원(선택). 지정하면 vec 길이와 불일치 시 건너뜀")

    def handle(self, *args, **opts):
        # 1) CSV 기본 경로: 컨테이너 마운트 경로 → BASE_DIR 순
        default_csv_candidates = [
            "/app/data/triptailor_full_metadata.csv",
            os.path.join(settings.BASE_DIR, "triptailor_full_metadata.csv"),
        ]
        csv_path = opts.get("csv")
        if not csv_path:
            for cand in default_csv_candidates:
                if os.path.exists(cand):
                    csv_path = cand
                    break

        if not csv_path or not os.path.exists(csv_path):
            raise CommandError(f"CSV not found. Tried: {csv_path or default_csv_candidates}")

        faiss_path = opts.get("faiss")
        batch_size = int(opts["batch"])
        no_embedding = bool(opts["no_embedding"])
        exp_dim = opts.get("dim")

        # 2) (선택) FAISS에서 벡터 복원
        vecs = None
        if not no_embedding and faiss_path:
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
                    if exp_dim is not None and vecs.shape[1] != exp_dim:
                        self.stderr.write(self.style.WARNING(
                            f"벡터 차원 불일치: index dim={vecs.shape[1]} vs --dim={exp_dim} → 임베딩 저장 건너뜀"
                        ))
                        vecs = None
                except Exception as e:
                    self.stderr.write(self.style.WARNING(
                        f"reconstruct_n 실패 → 임베딩 저장 건너뜀 (원본 임베딩 파일 필요). err={e}"
                    ))
                    vecs = None

        # 3) CSV 적재(업서트)
        self.stdout.write(self.style.MIGRATE_HEADING("Load CSV & upsert"))
        processed = 0
        created_cnt = 0
        updated_cnt = 0

        # 태그 캐시(성능)
        tag_cache = {t.name: t.id for t in Tag.objects.all().only("id", "name")}
        new_tags_buf = []

        def flush_new_tags():
            nonlocal new_tags_buf, tag_cache
            if not new_tags_buf:
                return
            uniq = list(dict.fromkeys(new_tags_buf))  # 중복 제거
            with transaction.atomic():
                for nt in uniq:
                    obj, _ = Tag.objects.get_or_create(name=nt)
                    tag_cache[obj.name] = obj.id
            new_tags_buf.clear()

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = row.get("명칭") or row.get("name")
                address = row.get("주소") or row.get("address")
                overview = row.get("개요") or row.get("overview")
                lat = row.get("위도") or row.get("lat")
                lng = row.get("경도") or row.get("lng")
                summary = row.get("summary", "")
                external_id = row.get("external_id") or None
                is_unique = str(row.get("is_unique", "0")).strip() in ["1", "True", "true"]
                raw_cls = row.get("class", "0")

                # 필수값 체크
                if not (name and address and overview and lat and lng):
                    continue

                # 수치 변환
                try:
                    lat = Decimal(str(lat))
                    lng = Decimal(str(lng))
                except Exception:
                    continue

                try:
                    place_class = int(float(str(raw_cls).replace(",", ".").strip() or 0))
                except ValueError:
                    place_class = 0

                region = address.split()[0] if address else ""

                # (선택) 임베딩
                embedding = None
                if vecs is not None and i < len(vecs):
                    cur = vecs[i]
                    if exp_dim is not None and cur.shape[0] != exp_dim:
                        # 차원 불일치 시 건너뛰기
                        pass
                    else:
                        embedding = cur.astype("float32").tolist()

                # upsert 기준: external_id가 있으면 그걸로, 없으면 (name, address)
                lookup = {}
                if external_id:
                    lookup["external_id"] = external_id
                else:
                    lookup["name"] = name
                    lookup["address"] = address

                defaults = {
                    "region": region,
                    "lat": lat,
                    "lng": lng,
                    "overview": overview,
                    "is_unique": is_unique,
                    "summary": summary,
                    "place_class": place_class,
                }
                if external_id:
                    defaults["name"] = name
                    defaults["address"] = address
                if embedding is not None:
                    defaults["embedding"] = embedding

                place, created = Place.objects.update_or_create(
                    **lookup,
                    defaults=defaults,
                )
                if created:
                    created_cnt += 1
                else:
                    updated_cnt += 1

                # 태그 처리(동기화)
                tag_str = row.get("tags", "")
                tag_names = [t.strip().lstrip("#") for t in tag_str.split() if t.strip()]
                # 미리 생성
                for tname in tag_names:
                    if tname not in tag_cache:
                        new_tags_buf.append(tname)

                if len(new_tags_buf) >= batch_size:
                    flush_new_tags()

                if tag_names:
                    ids = [tag_cache[t] for t in tag_names if t in tag_cache]
                    if ids:
                        place.tags.set(ids)  # 중복 없이 현재 행 기준으로 동기화

                processed += 1
                if processed % batch_size == 0:
                    self.stdout.write(f"- processed={processed} (created={created_cnt}, updated={updated_cnt})")

        # 남은 새 태그 생성
        flush_new_tags()

        self.stdout.write(self.style.SUCCESS(
            f"완료: processed={processed}, created={created_cnt}, updated={updated_cnt}"
        ))

        # 인덱스 안내
        if vecs is not None:
            self.stdout.write(self.style.HTTP_INFO(
                "임베딩 인덱스가 없다면 psql에서 생성:\n"
                "CREATE INDEX IF NOT EXISTS place_embedding_ivfflat "
                "ON places_place USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);\n"
                "ANALYZE places_place;"
            ))
