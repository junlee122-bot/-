"""Supabase 프로젝트 간 데이터 이전 (유료 → 무료).

PostgREST(REST API)로 source 프로젝트의 모든 테이블을 읽어 target 프로젝트에
복사한다. 두 프로젝트 모두 schema.sql 로 같은 테이블 구조여야 한다.

사전 준비:
  1) 새(무료) 프로젝트 생성 후 SQL Editor 에서 schema.sql 전체 실행
  2) 아래 환경변수 설정(.env 또는 셸):
       SRC_SUPABASE_URL, SRC_SERVICE_ROLE_KEY   (기존 유료)
       DST_SUPABASE_URL, DST_SERVICE_ROLE_KEY   (새 무료)

실행:
  python -m scripts.migrate_supabase            # 실제 복사
  python -m scripts.migrate_supabase --dry-run  # 행 수만 확인(쓰기 안 함)

특징:
  - 외래키 순서(teams→matches→자식들)대로 복사
  - 페이지네이션으로 대량 테이블(overseas_odds)도 안전
  - id(bigserial) 컬럼은 target 자동생성에 맡기려 제거하지 않고 그대로 복사
    (PK 충돌 방지를 위해 target은 비어 있어야 함; --truncate 로 비우기 가능)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from betman import env  # noqa: E402

# 외래키 의존성 순서 (부모 먼저)
TABLES = [
    "teams",
    "matches",
    "betman_offerings",
    "overseas_odds",
    "team_records",
    "picks",
    "pick_logs",
    "bets",
    "betman_manual_odds",
]

# bigserial PK 가 있는 테이블 — 복사 시 id 를 빼서 target 이 새로 부여하게 함
# (FK 가 id 를 참조하지 않으므로 안전. 참조는 모두 텍스트 키 사용.)
SERIAL_ID_TABLES = {
    "betman_offerings",
    "overseas_odds",
    "pick_logs",  # PK는 pick_id(text)지만 안전상 그대로 둠 → 제외
    "bets",
    "betman_manual_odds",
}
# pick_logs 는 text PK 이므로 id 제거 대상 아님
SERIAL_ID_TABLES.discard("pick_logs")

PAGE = 1000


def _req(url: str, key: str, method: str = "GET", body: bytes | None = None,
         extra_headers: dict | None = None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=60)


def fetch_all(base: str, key: str, table: str) -> list[dict]:
    import json
    rows: list[dict] = []
    offset = 0
    while True:
        url = f"{base}/rest/v1/{table}?select=*&limit={PAGE}&offset={offset}"
        try:
            with _req(url, key) as resp:
                batch = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{table} 읽기 실패 {e.code}: {e.read().decode()[:200]}")
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return rows


def insert_rows(base: str, key: str, table: str, rows: list[dict]) -> None:
    import json
    if not rows:
        return
    if table in SERIAL_ID_TABLES:
        rows = [{k: v for k, v in r.items() if k != "id"} for r in rows]
    # 청크로 나눠 삽입
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        body = json.dumps(chunk, ensure_ascii=False).encode("utf-8")
        url = f"{base}/rest/v1/{table}"
        try:
            _req(url, key, "POST", body,
                 {"Prefer": "return=minimal,resolution=merge-duplicates"}).close()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{table} 쓰기 실패 {e.code}: {e.read().decode()[:200]}")
        time.sleep(0.05)


def truncate(base: str, key: str, table: str) -> None:
    # 안전한 전체 삭제용 필터 (모든 행)
    url = f"{base}/rest/v1/{table}?id=not.is.null"
    # text PK 테이블 대비: id 없으면 pick_id/team_id 등으로 대체 시도
    for filt in ("id=not.is.null", "pick_id=not.is.null", "team_id=not.is.null",
                 "round_no=not.is.null"):
        try:
            _req(f"{base}/rest/v1/{table}?{filt}", key, "DELETE", None,
                 {"Prefer": "return=minimal"}).close()
            return
        except urllib.error.HTTPError:
            continue


def main() -> int:
    ap = argparse.ArgumentParser(description="Supabase 프로젝트 간 데이터 이전")
    ap.add_argument("--dry-run", action="store_true", help="행 수만 확인")
    ap.add_argument("--truncate", action="store_true",
                    help="복사 전 target 테이블 비우기")
    args = ap.parse_args()

    env.load_dotenv()
    src_url = os.environ.get("SRC_SUPABASE_URL")
    src_key = os.environ.get("SRC_SERVICE_ROLE_KEY")
    dst_url = os.environ.get("DST_SUPABASE_URL")
    dst_key = os.environ.get("DST_SERVICE_ROLE_KEY")

    if not (src_url and src_key):
        print("✗ SRC_SUPABASE_URL / SRC_SERVICE_ROLE_KEY 를 설정하세요.")
        return 1
    if not args.dry_run and not (dst_url and dst_key):
        print("✗ DST_SUPABASE_URL / DST_SERVICE_ROLE_KEY 를 설정하세요.")
        return 1

    print(f"source: {src_url}")
    print(f"target: {dst_url or '(dry-run)'}\n")

    total = 0
    for table in TABLES:
        rows = fetch_all(src_url.rstrip("/"), src_key, table)
        total += len(rows)
        if args.dry_run:
            print(f"  {table:<20} {len(rows)}행")
            continue
        if args.truncate:
            truncate(dst_url.rstrip("/"), dst_key, table)
        insert_rows(dst_url.rstrip("/"), dst_key, table, rows)
        print(f"  {table:<20} {len(rows)}행 복사 완료")

    print(f"\n{'행 합계' if args.dry_run else '이전 완료'}: {total}행")
    if not args.dry_run:
        print("다음: Vercel/.env/GitHub Secrets 의 SUPABASE_URL·KEY 를 새 값으로 교체하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
