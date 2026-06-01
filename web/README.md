# Betman Dashboard (Next.js)

Vercel 프로젝트용 웹 대시보드. Python 분석 레이어가 Firebase Firestore 의 `picks`
컬렉션에 적재한 결과를 읽어 종목별로 value 점수 순으로 표시합니다.

> 분석 로직(de-vig/EV/value/Elo)은 Python 엔진이 담당합니다. 이 앱은 **표시
> 전용**이라 분석 코드를 TypeScript로 중복 구현하지 않습니다.

## 데이터 흐름

```
Python (수집→분석)  →  Firestore: picks 컬렉션  →  Next.js 대시보드(서버 컴포넌트)
   run_full_pipeline                               getDashboardData()
```

## 로컬 개발

```bash
cd web
cp .env.local.example .env.local     # Firebase 서비스계정(base64) 채우기
pnpm install
pnpm dev            # http://localhost:3000
```

## Vercel 배포

1. **Root Directory**: `web` 로 설정 (모노레포이므로 중요).
2. **Environment Variables** 에 추가 (둘 중 하나):
   - `FIREBASE_SERVICE_ACCOUNT_BASE64 = <서비스계정 JSON 의 base64>` (권장)
   - 또는 `FIREBASE_SERVICE_ACCOUNT = {...JSON...}`
   - ⚠️ `NEXT_PUBLIC_` 접두어를 **붙이지 마세요**. 서버에서만 읽어 클라이언트로
     키가 노출되지 않습니다.
3. Framework Preset: **Next.js** (자동 감지).

서비스계정 base64 만들기:
```bash
base64 -w0 service-account.json   # 리눅스
base64 -i service-account.json    # mac
```

## 화면

- 환급률 63% 경고 배너 (장기 EV는 구조적 마이너스 — 베팅 권유 아님)
- 축구 / 야구 / 농구 기본 섹션, value 점수 순 + 비핵심 종목 '주목 픽'
- 각 픽: 베트맨 배당 / 공정확률(Pinnacle de-vig) / edge% / EV / value / 근거
- 핸디캡·언오버·SUM 은 `모델` 배지(포아송 추정)
- 라이트/다크 자동 테마

## 데이터가 안 보일 때

1. Firebase 서비스계정 환경변수가 맞는가 (base64 디코딩되는지)
2. `python -m scripts.run_full_pipeline` 로 `picks` 컬렉션을 적재했는가
3. Firestore 보안 규칙이 서버(admin) 접근을 막지 않는가 (admin SDK 는 규칙 우회)
