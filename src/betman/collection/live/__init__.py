"""라이브 데이터 어댑터 (실제 외부 API/피드).

- odds_api.py : The Odds API (해외 배당 + 경기 목록). Pinnacle 포함(eu 리전).
- rss_news.py : 정식 RSS 피드 기반 뉴스 수집.

정직성 명시: 베트맨 발매·고정배당과 정형 통계(xG/ERA 등)는 공개 API가 없어
라이브 모드에서도 mock 어댑터를 사용한다. 즉 라이브 = 실 해외배당 + 실 뉴스
+ mock(베트맨/통계). 소스 조립은 collection/sources.py 참고.
"""
