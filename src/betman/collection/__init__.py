"""1단계: 데이터 수집 레이어.

4개의 수집기 인터페이스(MatchCollector / OddsCollector / BetmanCollector /
NewsCollector)와 이를 종목 공통 포맷으로 묶는 파이프라인을 제공한다.
각 인터페이스는 mock → 유료 API 로 교체 가능하다.
"""
