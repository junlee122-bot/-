"""픽별 입력값/결과 로깅 (사후 검증용).

요구사항: "어떤 변수가 실제 적중에 기여했는지 사후 검증할 수 있게, 픽별로
사용한 입력값과 결과를 로그로 남겨라."

각 픽에 대해
  - 사용한 feature 값(결측 여부 포함) + 그때의 가중치
  - 베트맨 배당/선택지
  - (나중에 채워지는) 실제 결과·적중 여부
를 JSONL로 남긴다. 이 로그로 백테스트/가중치 재캘리브레이션을 수행한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..domain.enums import MarketType, Outcome, Sport
from ..domain.features import MatchFeatures, flatten_features
from .weights import weight_for


@dataclass
class FeatureValueLog:
    present: bool
    value: Any
    weight: float
    source: str


@dataclass
class PickInputSnapshot:
    """한 픽이 어떤 입력으로 만들어졌는지의 스냅샷."""

    pick_id: str
    match_id: str
    sport: Sport
    market: MarketType
    outcome: Outcome
    betman_odds: float
    captured_at: datetime
    features: dict[str, FeatureValueLog] = field(default_factory=dict)
    # 경기 후 채워지는 결과
    result_outcome: Optional[Outcome] = None
    hit: Optional[bool] = None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (Sport, MarketType, Outcome)):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def build_snapshot(
    *,
    pick_id: str,
    match_id: str,
    sport: Sport,
    market: MarketType,
    outcome: Outcome,
    betman_odds: float,
    match_features: MatchFeatures,
    captured_at: Optional[datetime] = None,
) -> PickInputSnapshot:
    """MatchFeatures를 평탄화해 종목별 가중치를 붙인 픽 스냅샷 생성."""
    snap = PickInputSnapshot(
        pick_id=pick_id,
        match_id=match_id,
        sport=sport,
        market=market,
        outcome=outcome,
        betman_odds=betman_odds,
        captured_at=captured_at or datetime.now(),
    )
    for name, feat in flatten_features(match_features).items():
        w = weight_for(sport, name)
        if w == 0.0 and not feat.present:
            continue  # 가중치도 없고 결측이면 로그 생략
        snap.features[name] = FeatureValueLog(
            present=feat.present,
            value=_jsonable(feat.value),
            weight=w,
            source=feat.source,
        )
    return snap


class JsonlPickLogger:
    """픽 스냅샷을 JSONL 파일에 누적. 결과는 별도 라인으로 append."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_pick(self, snapshot: PickInputSnapshot) -> None:
        record = {"type": "pick", **_jsonable(asdict(snapshot))}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_result(self, pick_id: str, result_outcome: Outcome, hit: bool) -> None:
        record = {
            "type": "result",
            "pick_id": pick_id,
            "result_outcome": result_outcome.value,
            "hit": hit,
            "recorded_at": datetime.now().isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
