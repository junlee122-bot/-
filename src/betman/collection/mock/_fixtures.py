"""mock 데이터 생성에 쓰는 종목별 팀/리그 풀과 공통 헬퍼."""

from __future__ import annotations

import hashlib

from ...domain.enums import Sport

# 종목별 (리그, [팀 이름...])
LEAGUES: dict[Sport, tuple[str, list[str]]] = {
    Sport.SOCCER: (
        "K리그1",
        ["울산", "전북", "포항", "수원FC", "강원", "대구", "인천", "광주"],
    ),
    Sport.BASEBALL: (
        "KBO",
        ["LG", "KT", "SSG", "NC", "두산", "KIA", "롯데", "삼성", "한화", "키움"],
    ),
    Sport.BASKETBALL: (
        "KBL",
        ["서울SK", "수원KT", "안양정관장", "창원LG", "부산KCC", "원주DB"],
    ),
    Sport.VOLLEYBALL: (
        "V리그",
        ["현대캐피탈", "대한항공", "OK저축은행", "삼성화재", "한국전력", "우리카드"],
    ),
    Sport.HOCKEY: (
        "아시아리그",
        ["HL안양", "사할린", "도호쿠", "닛코"],
    ),
    Sport.ESPORTS: (
        "LCK",
        ["T1", "GenG", "한화생명", "KT롤스터", "DK", "광동"],
    ),
}


def seed_from(*parts: str) -> int:
    """문자열들로부터 재현 가능한 정수 시드 생성."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)
