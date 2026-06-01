"""Supabase(Postgres) → Firebase Firestore 데이터 이전.

기존 Supabase 프로젝트의 모든 테이블을 읽어 Firestore 컬렉션으로 복사한다.
문서 ID 매핑:
  teams/{id}  matches/{id}  team_records/{team_id__venue}
  picks/{pick_id}  pick_logs/{pick_id}
  betman_offerings/overseas_odds/bets/betman_manual_odds → 자동 ID(시계열)

사전 준비(.env):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY        (기존, source)
  GOOGLE_APPLICATION_CREDENTIALS 또는
  FIREBASE_SERVICE_ACCOUNT(_BASE64)              (신규, target)

실행:
  python -m scripts.migrate_to_firestore --dry-run   # 행 수만
  python -m scripts.migrate_to_firestore             # 실제 복사
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from betman.config import load_firebase_settings, load_supabase_settings  # noqa: E402

# (테이블, 문서ID 키 또는 None=자동ID)
TABLES: list[tuple[str, str | None]] = [
    ("teams", "id"),
    ("matches", "id"),
    ("team_records", None),       # team_id__venue 로 합성
    ("picks", "pick_id"),
    ("pick_logs", "pick_id"),
    ("betman_offerings", None),
    ("overseas_odds", None),
    ("bets", None),
    ("betman_manual_odds", None),
]
PAGE = 1000


def fetch_all(base: str, key: str, table: str) -> list[dict]:
    import json
    rows: list[dict] = []
    offset = 0
    while True:
        url = f"{base}/rest/v1/{table}?select=*&limit={PAGE}&offset={offset}"
        req = urllib.request.Request(
            url, headers={"apikey": key, "Authorization": f"Bearer {key}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                batch = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{table} 읽기 실패 {e.code}: {e.read().decode()[:160]}")
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Supabase → Firestore 이전")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sb = load_supabase_settings()
    if not sb.configured:
        print("✗ SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 설정 필요(source)")
        return 1
    base, key = sb.url.rstrip("/"), sb.write_key

    db = None
    if not args.dry_run:
        fb = load_firebase_settings()
        if not fb.configured:
            print("✗ Firebase 서비스계정 설정 필요(target)")
            return 1
        from betman.storage.firestore_repo import FirestoreMatchRepository
        db = FirestoreMatchRepository(fb)._db

    print(f"source(Supabase): {base}")
    print(f"target(Firestore): {'(dry-run)' if args.dry_run else 'configured'}\n")

    total = 0
    for table, id_key in TABLES:
        rows = fetch_all(base, key, table)
        total += len(rows)
        if args.dry_run:
            print(f"  {table:<20} {len(rows)}행")
            continue
        # 배치 쓰기
        for i in range(0, len(rows), 450):
            batch = db.batch()
            for r in rows[i:i + 450]:
                if table == "team_records":
                    doc_id = f"{r.get('team_id')}__{r.get('venue')}"
                elif id_key:
                    doc_id = str(r.get(id_key))
                else:
                    doc_id = None
                ref = (
                    db.collection(table).document(doc_id)
                    if doc_id else db.collection(table).document()
                )
                # bigserial id 는 Firestore 에서 불필요 → 제거
                r2 = {k: v for k, v in r.items() if k != "id"}
                batch.set(ref, r2)
            batch.commit()
        print(f"  {table:<20} {len(rows)}행 복사 완료")

    print(f"\n{'행 합계' if args.dry_run else '이전 완료'}: {total}행")
    if not args.dry_run:
        print("다음: Vercel/.env/GitHub Secrets 를 Firebase 자격으로 교체하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
