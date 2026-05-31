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

## 🌐 가장 쉬운 방법: 웹 대시보드 입력 (권장)

대시보드 상단의 **"베트맨 발매표 입력 →"** (`/betman`) 페이지에서:

1. 종목·회차 선택
2. 베트맨 발매 화면을 **드래그·복사 → 붙여넣기**
3. 미리보기로 승/무/패 배당 확인 → **저장**

**모든 마켓**(승무패·핸디캡·소수핸디캡·언더오버·SUM)을 인식해 저장합니다.
저장된 배당은 `betman_manual_odds` 테이블에 들어가며, 다음 분석 실행(매일 자동
또는 수동 `run_full_pipeline`) 때 팀명으로 실제 경기와 매칭됩니다.

**파생 마켓 평가 방식**: 핸디캡·언오버·SUM은 Pinnacle이 직접 발매하지 않거나
기준선이 달라 직접 비교가 어렵습니다. 그래서 **Pinnacle 기준확률 → 포아송 득점
모델(λ 역산) → 파생 마켓 공정확률**을 계산해 edge/EV를 평가합니다.

- **축구·하키**(3갈래): 1X2 공정확률로 λ 역산
- **야구**(2갈래): 머니라인 + 리그 평균 총득점(≈9점) 힌트로 λ 역산 → 런라인
  (핸디캡 ±1.5)·언더오버 지원
- **농구**: 점수 스케일이 커 포아송이 부적합 → 파생 마켓 미지원(머니라인만)

이는 **모델 추정값**이라 Pinnacle 직접 확률(1X2/머니라인)보다 신뢰도를 낮춰
(×0.6) 반영하며, 대시보드/로그에 `model_based` 로 표시됩니다.

> 분석 실행 시 환경변수: `BETMAN_SOURCE=supabase` (웹 입력을 읽음).
> 특정 회차만 보려면 `BETMAN_ROUND=8994`.

⚠️ **사전 준비**: `schema.sql` 의 `betman_manual_odds` 테이블을 Supabase SQL
Editor 에서 한 번 실행해야 합니다(신규 테이블).

## ⚡ 터미널 입력: 붙여넣기 파서

CSV를 한 줄씩 손으로 적지 말고, **베트맨 발매 화면에서 텍스트를 드래그·복사**해
붙여넣으면 자동으로 CSV가 만들어집니다.

```bash
python -m scripts.betman_paste --round 2610 --sport baseball
# → 붙여넣고 Ctrl-D. 파싱 결과 미리보기 후 y 로 저장.
```

여러 종목을 한 회차 파일에 모으려면 `--append`:

```bash
python -m scripts.betman_paste --round 2610 --sport soccer --append
```

**인식하는 형식**(섞여 있어도 됨):
- `삼성 라이온즈 1.95 두산 베어스 1.78`  (팀-배당-팀-배당)
- `삼성 라이온즈 vs 두산 베어스 1.95 1.78`  (vs 구분)
- `Arsenal 1.95 3.60 4.10 Chelsea`  (배당 3개 = 축구 승무패)
- 여러 줄(팀/배당 줄바꿈)도 인식. 경기 사이는 **빈 줄**로 구분하면 가장 정확.

배당 개수로 종목을 자동 판별합니다(2개=승패, 3개=승무패). 한글 팀명은
`aliases.json` 으로 영문 변환되어 The Odds API 경기와 매칭됩니다. 미인식 블록은
표에 따로 표시되니 그것만 수동 보정하세요.

## 효율적인 수기 입력 요령

1. 베트맨 **발매중 게임** 화면에서 한 종목씩 표 영역을 드래그·복사
2. `betman_paste` 에 붙여넣기 → 미리보기로 팀명/배당 확인
3. 영문 매칭 안 된 팀이 있으면 `aliases.json` 에 한 줄 추가 후 재실행
4. 다음 종목은 `--append` 로 같은 회차 파일에 누적

## 수동 편집 (대안)

`round_example.csv` 를 복사해 직접 편집해도 됩니다. 저장 후:

```bash
DATA_SOURCE_MODE=live BETMAN_SOURCE=csv python -m scripts.run_full_pipeline
```
