# 베트맨 발매표 수동 입력

베트맨(프로토 승부식)은 공식 배당 API가 없어, 회차별 발매표를 여기에 CSV(또는
JSON)로 적어 넣으면 파이프라인이 읽어 분석에 반영합니다. **이게 들어와야
edge/EV 가 진짜 의미를 갖습니다** (없으면 베트맨 배당은 mock).

> ⚠️ 이 폴더의 `*.csv`/`*.json` 은 `.gitignore` 됩니다(개인 데이터). 단, 예시
> 파일 `round_example.csv` 와 `aliases.json` 은 커밋됩니다.

## CSV 형식

```
round_no,sport,home,away,market,outcome,odds
```

| 컬럼 | 설명 |
|------|------|
| round_no | 베트맨 회차 (예: 2610) |
| sport | soccer / baseball / basketball / volleyball / hockey / esports |
| home, away | 팀명. **The Odds API 영문 팀명과 같게** 쓰거나 `aliases.json` 으로 매핑 |
| market | 비우면 종목 기본값 (축구/하키=1x2, 그 외=moneyline) |
| outcome | home / draw / away |
| odds | 베트맨 고정배당(십진). 예 1.95 |
| sales_open | (선택) true/false, 기본 true |

한 경기 = 여러 줄(선택지마다 1줄). 축구는 home/draw/away 3줄, 야구·농구는 2줄.

## 팀명 매칭

The Odds API 경기와 잇는 키가 팀명뿐이라, **영문 팀명을 그대로 쓰는 게 가장
안전**합니다. 한글로 쓰려면 `aliases.json` 에 매핑을 넣으세요:

```json
{ "삼성 라이온즈": "Samsung Lions", "두산 베어스": "Doosan Bears" }
```

## 사용

```bash
# 발매표를 data/betman/round_2610.csv 로 저장한 뒤
DATA_SOURCE_MODE=live BETMAN_SOURCE=csv python -m scripts.run_full_pipeline
```

`round_example.csv` 를 복사해 시작하세요.
