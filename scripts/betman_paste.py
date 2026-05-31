"""베트맨 발매표 '붙여넣기 → CSV' 파서.

CSV를 한 줄씩 손으로 적는 대신, 베트맨 발매 화면에서 텍스트를 드래그·복사해
붙여넣으면 home/draw/away + 배당을 자동 추출해 CSV로 저장한다.

핵심 아이디어
  - 베트맨 발매표는 팀명과 배당(소수)이 한 덩어리로 복사된다.
  - 한 경기 블록에서 '소수점 숫자(배당)'들과 '팀명(한글/영문)'을 분리해,
    배당 개수로 종목(2개=승패, 3개=승무패)을 판별한다.
  - aliases.json 으로 한글 팀명을 The Odds API 영문명으로 변환(매칭 위해).
  - 파싱 결과를 표로 보여주고, 확인 후에만 CSV로 저장(사람 검수 단계).

사용
  python -m scripts.betman_paste --round 2610 --sport baseball
  # 실행하면 붙여넣기 입력을 받음. 한 경기씩 또는 통째로 붙여넣고,
  # 빈 줄 두 번(또는 Ctrl-D)으로 입력 종료.

지원 입력 형태(유연하게 인식):
  1) 한 줄에 다 있는 경우:
     "삼성 라이온즈 1.95 두산 베어스 1.78"
     "Arsenal 1.95 3.60 4.10 Chelsea"        (3배당=승무패)
  2) 여러 줄:
     삼성 라이온즈
     1.95
     두산 베어스
     1.78
  3) vs 구분:
     "삼성 라이온즈 vs 두산 베어스  1.95 1.78"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 십진 배당 패턴: 1.01 ~ 99.99 정도. 정수 스코어/순위와 구분 위해 소수점 필수.
_ODDS_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\b")
_VALID_SPORTS = {
    "soccer", "baseball", "basketball", "volleyball", "hockey", "esports",
}
# 무승부가 있는(3갈래) 종목
_HAS_DRAW = {"soccer", "hockey"}


def _load_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_team(s: str) -> str:
    """팀명 후보 정리: 양끝 공백/구분기호 제거(분리는 parse_block 에서)."""
    s = s.strip(" \t|-—·,")
    return re.sub(r"\s+", " ", s)


def parse_block(text: str) -> dict | None:
    """한 경기 블록(여러 줄 가능) → {home, away, odds:[...]} 또는 None.

    전략: 텍스트에서 배당(소수)들을 추출하고, 배당이 아닌 토큰 덩어리를
    팀명 후보로 본다. 팀명은 보통 2개(home, away)다.
    """
    flat = " ".join(text.split())
    if not flat:
        return None

    odds = [float(x) for x in _ODDS_RE.findall(flat)]
    # 배당 위치를 기준으로 텍스트를 쪼개 팀명 후보 추출
    parts = _ODDS_RE.split(flat)
    teams: list[str] = []
    for p in parts:
        t = _clean_team(p)
        if not t or t.replace(".", "").isdigit():
            continue
        # 한 토큰 안에 'vs' 또는 구분자로 두 팀이 붙어 있으면 분리
        for sub in re.split(r"\s+vs\.?\s+|\s{2,}|[|/]", t, flags=re.IGNORECASE):
            sub = sub.strip()
            if len(sub) >= 2 and not sub.replace(".", "").isdigit():
                teams.append(sub)

    if len(teams) < 2 or len(odds) < 2:
        return None

    home, away = teams[0], teams[-1]
    return {"home": home, "away": away, "odds": odds}


def block_to_rows(
    block: dict, sport: str, round_no: str, aliases: dict[str, str]
) -> list[dict]:
    """파싱된 블록 → CSV 행들. 배당 개수로 승무패/승패 판별."""
    home = aliases.get(block["home"], block["home"])
    away = aliases.get(block["away"], block["away"])
    odds = block["odds"]
    rows: list[dict] = []

    if sport in _HAS_DRAW and len(odds) >= 3:
        outcomes = [("home", odds[0]), ("draw", odds[1]), ("away", odds[2])]
    else:
        # 2갈래: 앞/뒤 배당을 home/away 로
        outcomes = [("home", odds[0]), ("away", odds[-1])]

    for oc, od in outcomes:
        rows.append({
            "round_no": round_no,
            "sport": sport,
            "home": home,
            "away": away,
            "market": "",
            "outcome": oc,
            "odds": od,
        })
    return rows


def split_blocks(raw: str) -> list[str]:
    """입력 전체를 경기 블록으로 분할.

    빈 줄을 경계로 본다. 빈 줄이 없으면 줄 단위로 '팀-배당' 묶음을 추정해
    각 줄을 한 블록으로 시도한다(한 줄=한 경기 형태 지원).
    """
    raw = raw.strip()
    if not raw:
        return []
    if "\n\n" in raw:
        return [b for b in raw.split("\n\n") if b.strip()]
    # 빈 줄 경계가 없으면: 각 줄이 배당 2개 이상을 포함하면 줄=블록
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    line_blocks = [ln for ln in lines if len(_ODDS_RE.findall(ln)) >= 2]
    if line_blocks and len(line_blocks) == len(lines):
        return lines
    # 그 외엔 전체를 한 블록으로
    return [raw]


def read_paste() -> str:
    print("발매표를 붙여넣으세요. 끝나면 빈 줄에서 Ctrl-D(또는 Ctrl-Z, Enter):",
          file=sys.stderr)
    return sys.stdin.read()


def main() -> int:
    ap = argparse.ArgumentParser(description="베트맨 발매표 붙여넣기 → CSV")
    ap.add_argument("--round", required=True, help="베트맨 회차 (예: 2610)")
    ap.add_argument("--sport", required=True, choices=sorted(_VALID_SPORTS))
    ap.add_argument("--out", default=None,
                    help="출력 CSV 경로 (기본: data/betman/round_<회차>.csv)")
    ap.add_argument("--aliases", default="data/betman/aliases.json")
    ap.add_argument("--append", action="store_true",
                    help="기존 파일에 이어붙임(여러 종목을 한 회차 파일에)")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="확인 프롬프트 없이 바로 저장")
    args = ap.parse_args()

    aliases = _load_aliases(Path(args.aliases))
    raw = read_paste()
    blocks = split_blocks(raw)

    all_rows: list[dict] = []
    parsed, failed = 0, []
    for b in blocks:
        pb = parse_block(b)
        if pb is None:
            failed.append(b.strip()[:60])
            continue
        all_rows.extend(block_to_rows(pb, args.sport, args.round, aliases))
        parsed += 1

    if not all_rows:
        print("\n✗ 인식된 경기가 없습니다. 형식을 확인하세요.", file=sys.stderr)
        if failed:
            print("  실패한 블록 예:", file=sys.stderr)
            for f in failed[:3]:
                print(f"    {f!r}", file=sys.stderr)
        return 1

    # 검수용 미리보기
    print(f"\n=== 파싱 결과: {parsed}경기 / {len(all_rows)}행 ===")
    cur = None
    for r in all_rows:
        key = (r["home"], r["away"])
        if key != cur:
            cur = key
            print(f"\n  {r['home']} vs {r['away']}  [{r['sport']}]")
        print(f"    {r['outcome']:<5} {r['odds']}")
    if failed:
        print(f"\n  ⚠ 인식 실패 {len(failed)}블록 (수동 확인 필요):")
        for f in failed[:5]:
            print(f"    {f!r}")

    # 확인 (--yes 면 건너뜀)
    if not args.yes:
        try:
            ans = input("\n이대로 CSV에 저장할까요? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans != "y":
            print("취소했습니다. (--yes 로 바로 저장 가능)")
            return 0

    out = Path(args.out or f"data/betman/round_{args.round}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_header = not (args.append and out.exists())
    mode = "a" if args.append and out.exists() else "w"
    import csv as _csv
    with out.open(mode, encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(
            fh,
            fieldnames=["round_no", "sport", "home", "away", "market",
                        "outcome", "odds"],
        )
        if write_header:
            w.writeheader()
        w.writerows(all_rows)
    print(f"✓ {out} 에 {len(all_rows)}행 저장 ({mode=}).")
    print("  팀명이 영문 매칭이 안 되면 data/betman/aliases.json 에 별칭을 추가하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
