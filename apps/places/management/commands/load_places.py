import os
import sys
import csv
import re
import time
from datetime import timedelta
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

_num_re = re.compile(r'^[\+\-]?\d+(\.\d+)?$')


def to_bool(v) -> bool:
    if v is None:
        return False
    # 숫자형은 그대로 판단
    if isinstance(v, (int, float)):
        return float(v) != 0.0
    # 문자열/그 외 → 정규화
    s = str(v).strip().lower()
    # 숫자 문자열(정수/소수) 처리: "1", "1.0", "0.0", "+2", "-0.0" 등
    if _num_re.match(s):
        try:
            return float(s) != 0.0
        except Exception:
            return False
    # 그 외 truthy 토큰
    return s in {"1", "true", "t", "y", "yes", "on"}

class Command(BaseCommand):
    help = "CSV(필수) + (선택) FAISS index에서 Place 및 임베딩을 DB에 적재 (진행률/ETA/막대 표시)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=False, help="CSV 경로 (기본: BASE_DIR/triptailor_full_metadata.csv)")
        parser.add_argument("--faiss", required=False, help="FAISS .index 경로 (벡터 저장 시)")
        parser.add_argument("--dim", type=int, default=None, help="임베딩 차원(옵션, 검증용)")
        parser.add_argument("--batch", type=int, default=500, help="태그 배치 커밋 간격")
        parser.add_argument("--log-interval", type=int, default=200, help="몇 건마다 진행 로그를 강제 출력할지")
        parser.add_argument("--bar-width", type=int, default=40, help="진행 막대 너비(칸 수)")
        parser.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 파싱/속도만 확인")
        parser.add_argument("--skip-embedding", action="store_true", help="FAISS 임베딩 저장 건너뛰기")

    # === 내부 유틸 ===
    def _fmt_hms(self, seconds: float) -> str:
        return str(timedelta(seconds=int(max(0, seconds))))

    def _eta(self, done: int, total: int, start_ts: float) -> tuple[str, str]:
        elapsed = time.time() - start_ts
        rate = done / elapsed if elapsed > 0 and done > 0 else 0
        remain = (total - done) / rate if rate > 0 else 0
        return self._fmt_hms(remain), self._fmt_hms(elapsed)

    def _bar(self, pct: float, width: int) -> str:
        filled = int(round(pct * width))
        return "[" + "#" * filled + "-" * (width - filled) + "]"

    def _print_progress(self, i: int, total: int, start_ts: float,
                        created: int, updated: int, skipped: int, bar_width: int,
                        final: bool = False):
        pct = (i / total) if total > 0 else 0.0
        eta, elapsed = self._eta(i, total, start_ts)
        line = (
            f"{self._bar(pct, bar_width)} "
            f"{pct*100:6.2f}%  "
            f"{i}/{total}  "
            f"elapsed={elapsed}  eta={eta}  "
            f"ok={created+updated} created={created} updated={updated} skipped={skipped}"
        )
        # 진행 중엔 같은 줄 덮어쓰기(\r), 종료 시 개행
        end = "\n" if final else "\r"
        # Django OutputWrapper는 carriage return도 전달 가능
        self.stdout.write(line, ending=end)
        self.stdout.flush()

    def handle(self, *args, **opts):
        csv_path = opts["csv"] or os.path.join(settings.BASE_DIR, "triptailor_full_metadata.csv")
        faiss_path = opts.get("faiss")
        dim_expect = opts.get("dim")
        batch_size = opts["batch"]
        log_interval = max(1, opts["log_interval"])
        bar_width = max(10, opts["bar_width"])
        dry_run = opts["dry_run"]
        skip_vec = opts["skip_embedding"]

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV not found: {csv_path}")

        # 0) CSV 총 행수(진행률 위해 미리 카운트)
        self.stdout.write(self.style.MIGRATE_HEADING("Count CSV rows"))
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            total_rows = sum(1 for _ in csv.DictReader(f))
        if total_rows == 0:
            raise CommandError("CSV에 데이터가 없습니다.")
        self.stdout.write(f"- total rows: {total_rows}")

        # 1) (선택) FAISS에서 벡터 복원
        vecs = None
        if faiss_path and not skip_vec:
            if not FAISS_AVAILABLE:
                self.stderr.write(self.style.WARNING("faiss 모듈이 없어 임베딩은 건너뜁니다. (pip install faiss-cpu)"))
            elif not os.path.exists(faiss_path):
                self.stderr.write(self.style.WARNING(f"FAISS index가 없어 임베딩은 건너뜁니다: {faiss_path}"))
            else:
                self.stdout.write(self.style.MIGRATE_HEADING("Load FAISS index"))
                index = faiss.read_index(faiss_path)
                n = index.ntotal
                self.stdout.write(f"- index.ntotal: {n}")
                if dim_expect:
                    try:
                        d = index.d
                        if d != dim_expect:
                            self.stderr.write(self.style.WARNING(f"임베딩 차원 불일치: index.d={d}, --dim={dim_expect}"))
                    except Exception:
                        pass
                try:
                    vecs = index.reconstruct_n(0, n)  # (n, d) float32
                except Exception as e:
                    self.stderr.write(self.style.WARNING(
                        f"reconstruct_n 실패 → 임베딩 저장 건너뜀 (원본 임베딩 파일 필요). err={e}"
                    ))
                    vecs = None

        # 2) CSV 적재
        self.stdout.write(self.style.MIGRATE_HEADING("Load CSV & upsert (progress bar)"))

        created = 0
        updated = 0
        skipped = 0
        processed_rows = 0

        # 태그 캐시(성능)
        tag_cache = {t.name: t.id for t in Tag.objects.all().only("id", "name")}
        new_tags: list[str] = []

        start_ts = time.time()
        last_tick = 0.0  # 초당 1회 이상 과도 출력 방지

        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader, start=1):
                    name = row.get("명칭")
                    address = row.get("주소")
                    overview = row.get("개요")
                    lat = row.get("위도") or row.get("lat")
                    lng = row.get("경도") or row.get("lng")
                    summary = row.get("summary", "")
                    external_id = row.get("external_id", None)
                    is_unique_raw = row.get("is_unique") or row.get("unique") or row.get("isunique") or 0
                    is_unique = to_bool(is_unique_raw)
                    raw_cls = row.get("class", "0")

                    # 필수 필드 검증
                    if not (name and address and overview and lat and lng):
                        skipped += 1
                        processed_rows += 1
                        # 진행 표시(스로틀링: 1초/혹은 간격)
                        now = time.time()
                        if (i % log_interval == 0) or (now - last_tick >= 1.0) or (i == total_rows):
                            self._print_progress(i, total_rows, start_ts, created, updated, skipped, bar_width)
                            last_tick = now
                        continue

                    try:
                        place_class = int(float(str(raw_cls).replace(",", ".").strip() or 0))
                    except ValueError:
                        place_class = 0

                    try:
                        lat = Decimal(lat)
                        lng = Decimal(lng)
                    except Exception:
                        skipped += 1
                        processed_rows += 1
                        now = time.time()
                        if (i % log_interval == 0) or (now - last_tick >= 1.0) or (i == total_rows):
                            self._print_progress(i, total_rows, start_ts, created, updated, skipped, bar_width)
                            last_tick = now
                        continue

                    region = address.split()[0] if address else ""

                    # (선택) 임베딩
                    embedding = None
                    if vecs is not None and (i - 1) < len(vecs):
                        embedding = vecs[i - 1].astype("float32").tolist()

                    if not dry_run:
                        defaults = {
                            "region": region,
                            "lat": lat,
                            "lng": lng,
                            "overview": overview,
                            "external_id": external_id,
                            "is_unique": is_unique,
                            "summary": summary,
                            "place_class": place_class,
                        }
                        if embedding is not None:
                            defaults["embedding"] = embedding

                        place, was_created = Place.objects.update_or_create(
                            name=name,
                            address=address,
                            defaults=defaults,
                        )
                        db_val = Place.objects.filter(pk=place.pk).values_list("is_unique", flat=True).first()
                        if db_val != is_unique:
                            self.stderr.write(self.style.WARNING(
                                f"[is_unique MISMATCH] name={name} addr={address} parsed={is_unique} db={db_val}"
                            ))
                        created += int(was_created)
                        updated += int(not was_created)

                        # 태그 처리
                        tag_str = row.get("tags", "")
                        tag_names = [t.strip().lstrip("#") for t in tag_str.split() if t.strip()]

                        for tname in tag_names:
                            tid = tag_cache.get(tname)
                            if tid is None:
                                new_tags.append(tname)

                        # 새 태그 배치 생성
                        if new_tags and len(new_tags) >= batch_size:
                            with transaction.atomic():
                                for nt in new_tags:
                                    obj, _ = Tag.objects.get_or_create(name=nt)
                                    tag_cache[obj.name] = obj.id
                            new_tags.clear()

                        if tag_names:
                            ids = [tag_cache[t] for t in tag_names if t in tag_cache]
                            if ids:
                                place.tags.add(*ids)

                    processed_rows += 1

                    # 진행 표시(스로틀링: 1초/혹은 간격)
                    now = time.time()
                    if (i % log_interval == 0) or (now - last_tick >= 1.0) or (i == total_rows):
                        self._print_progress(i, total_rows, start_ts, created, updated, skipped, bar_width)
                        last_tick = now

        except KeyboardInterrupt:
            # 줄 깨끗이 정리
            sys.stdout.write("\n")
            sys.stdout.flush()
            self.stderr.write(self.style.WARNING("사용자에 의해 중단됨(KeyboardInterrupt). 진행 상황을 요약합니다."))

        # 남은 새 태그 처리
        if not dry_run and new_tags:
            with transaction.atomic():
                for nt in new_tags:
                    obj, _ = Tag.objects.get_or_create(name=nt)
                    tag_cache[obj.name] = obj.id

        # 최종 진행줄 한 줄 마무리 출력(개행)
        self._print_progress(processed_rows, total_rows, start_ts, created, updated, skipped, bar_width, final=True)

        # 요약
        self.stdout.write(self.style.SUCCESS(
            f"완료 ✅ total={total_rows}, ok={created+updated}, created={created}, updated={updated}, skipped={skipped}"
        ))

        # 인덱스 안내
        if not dry_run and (faiss_path and not skip_vec and vecs is not None):
            self.stdout.write(self.style.HTTP_INFO(
                "임베딩 인덱스가 없다면 psql에서 생성:\n"
                "CREATE INDEX IF NOT EXISTS place_embedding_ivfflat "
                "ON places_place USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);\n"
                "ANALYZE places_place;"
            ))
