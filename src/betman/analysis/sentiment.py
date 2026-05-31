"""비정형 → 신호 플래그 변환 (LLM 보조 가중치).

프롬프트 요구: "부상 뉴스·분석글 같은 비정형 정보는 LLM으로 항목 플래그(예:
'주전 공격수 결장', '백투백')로 환산해 보조 가중치로만 반영."

설계:
  - SentimentClassifier 인터페이스(analysis/base.py)를 두 가지로 구현.
  - RuleBasedSentimentClassifier: LLM 없이도 동작하는 키워드 기반 폴백
    (프로토타입/오프라인/무료 모드). 한국어 키워드로 결장·복귀·부진·호조 등을
    분류해 SentimentFlag 생성.
  - LLMSentimentClassifier: anthropic SDK로 뉴스 원문을 요약·분류(키 있을 때).
    프롬프트 캐싱으로 시스템 지침을 캐싱.

신호는 value 점수에 '보조 가중치로만' 반영된다(정형 지표를 대체하지 않음).
"""

from __future__ import annotations

import os

from ..domain.enums import Outcome, SignalPolarity
from ..domain.models import NewsItem, NormalizedMatchBundle, SentimentFlag
from .base import SentimentClassifier

# 키워드 → (극성, 대략적 신뢰도). 한국어 mock 뉴스에 맞춤.
_POSITIVE_KW = {
    "복귀": 0.6, "회복": 0.55, "출전 유력": 0.6, "자신감": 0.4,
    "승리": 0.4, "상승": 0.45, "호조": 0.5,
}
_NEGATIVE_KW = {
    "결장": 0.7, "부상": 0.6, "이탈": 0.65, "징계": 0.7, "연패": 0.55,
    "저조": 0.5, "부진": 0.55, "약세": 0.5, "우려": 0.4,
}
# 일정/구조 플래그(보조)
_FLAG_KW = {
    "백투백": ("back_to_back", 0.6),
    "원정": ("away_heavy", 0.3),
    "더비": ("derby", 0.4),
}


def _target_outcome(text: str, bundle: NormalizedMatchBundle) -> Outcome:
    """기사에 어느 팀이 언급됐는지로 신호 대상 선택지 추정."""
    home = bundle.match.home.name
    away = bundle.match.away.name
    if home in text and away not in text:
        return Outcome.HOME
    if away in text and home not in text:
        return Outcome.AWAY
    return Outcome.HOME  # 모호하면 홈 기준(보조 신호라 영향 제한적)


class RuleBasedSentimentClassifier(SentimentClassifier):
    """키워드 기반 폴백 분류기 (LLM/네트워크 불필요)."""

    def classify(self, bundle: NormalizedMatchBundle) -> list[SentimentFlag]:
        flags: list[SentimentFlag] = []
        for item in bundle.news:
            text = f"{item.title} {item.body}"
            target = _target_outcome(text, bundle)

            best_polarity = SignalPolarity.NEUTRAL
            best_conf = 0.0
            summary = item.title

            for kw, conf in _NEGATIVE_KW.items():
                if kw in text and conf > best_conf:
                    best_polarity, best_conf = SignalPolarity.NEGATIVE, conf
            for kw, conf in _POSITIVE_KW.items():
                if kw in text and conf > best_conf:
                    best_polarity, best_conf = SignalPolarity.POSITIVE, conf

            if best_conf > 0:
                flags.append(
                    SentimentFlag(
                        target_outcome=target,
                        polarity=best_polarity,
                        confidence=best_conf,
                        summary=summary,
                        source_url=item.url,
                    )
                )
        return flags


class LLMSentimentClassifier(SentimentClassifier):
    """anthropic SDK 기반 분류기. ANTHROPIC_API_KEY 없으면 규칙 기반으로 폴백."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self._model = model
        self._fallback = RuleBasedSentimentClassifier()

    def classify(self, bundle: NormalizedMatchBundle) -> list[SentimentFlag]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self._fallback.classify(bundle)
        try:
            return self._classify_llm(bundle)
        except Exception:
            # 네트워크/쿼터 문제 시 안전하게 폴백
            return self._fallback.classify(bundle)

    def _classify_llm(self, bundle: NormalizedMatchBundle) -> list[SentimentFlag]:
        import json

        import anthropic

        client = anthropic.Anthropic()
        home, away = bundle.match.home.name, bundle.match.away.name
        articles = [
            {"title": n.title, "body": n.body, "url": n.url} for n in bundle.news
        ]
        if not articles:
            return []

        system = (
            "너는 스포츠 베팅 분석 보조다. 뉴스/분석글을 읽고 각 글이 어느 팀"
            "(home/away)에 우호적/불리한지 분류한다. 정형 지표를 대체하지 않는"
            " '보조 신호'만 만든다. 반드시 JSON 배열로만 답한다. 각 원소:"
            ' {"target":"home|away","polarity":"positive|negative|neutral",'
            '"confidence":0~1,"summary":"한 줄 요약"}'
        )
        user = json.dumps(
            {"home": home, "away": away, "articles": articles}, ensure_ascii=False
        )

        resp = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},  # 지침 캐싱
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in resp.content if block.type == "text"
        )
        data = json.loads(text)

        out: list[SentimentFlag] = []
        for d in data:
            target = (
                Outcome.HOME if str(d.get("target")).lower() == "home"
                else Outcome.AWAY
            )
            pol = {
                "positive": SignalPolarity.POSITIVE,
                "negative": SignalPolarity.NEGATIVE,
            }.get(str(d.get("polarity")).lower(), SignalPolarity.NEUTRAL)
            out.append(
                SentimentFlag(
                    target_outcome=target,
                    polarity=pol,
                    confidence=float(d.get("confidence", 0.3)),
                    summary=str(d.get("summary", "")),
                )
            )
        return out
