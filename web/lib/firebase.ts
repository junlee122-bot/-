import {
  initializeApp,
  getApps,
  cert,
  App,
  ServiceAccount,
} from "firebase-admin/app";
import { getFirestore, Firestore } from "firebase-admin/firestore";

// 서버 전용 Firebase Admin (Firestore).
// 서비스계정 키는 서버에서만 사용하며 클라이언트로 절대 노출하지 않는다
// (NEXT_PUBLIC_ 접두어를 쓰지 않음).
//
// 환경변수 (택1):
//   FIREBASE_SERVICE_ACCOUNT        서비스계정 JSON 문자열
//   FIREBASE_SERVICE_ACCOUNT_BASE64 위 JSON 의 base64 (Vercel 한 줄 입력용)
let _db: Firestore | null = null;

function parseServiceAccount(): Record<string, string> {
  const b64 = process.env.FIREBASE_SERVICE_ACCOUNT_BASE64;
  const json = process.env.FIREBASE_SERVICE_ACCOUNT;

  // 1) base64 우선: 공백/줄바꿈 제거 후 디코딩 → JSON 파싱
  if (b64 && b64.trim()) {
    const cleaned = b64.replace(/\s+/g, "");
    let decoded: string;
    try {
      decoded = Buffer.from(cleaned, "base64").toString("utf-8");
    } catch {
      throw new Error("FIREBASE_SERVICE_ACCOUNT_BASE64 디코딩 실패");
    }
    // 디코딩 결과가 '{' 로 시작하지 않으면 base64 값이 손상된 것
    if (!decoded.trimStart().startsWith("{")) {
      throw new Error(
        "FIREBASE_SERVICE_ACCOUNT_BASE64 값이 손상되었습니다(디코딩 결과가 JSON이 " +
          "아님). Vercel 환경변수에 base64 전체를 공백 없이 다시 붙여넣으세요."
      );
    }
    return JSON.parse(decoded);
  }

  // 2) JSON 문자열 직접
  if (json && json.trim()) {
    return JSON.parse(json);
  }

  throw new Error(
    "Firebase 미설정: FIREBASE_SERVICE_ACCOUNT_BASE64(권장) 또는 " +
      "FIREBASE_SERVICE_ACCOUNT 환경변수를 설정하세요."
  );
}

function loadServiceAccount(): ServiceAccount {
  const parsed = parseServiceAccount();
  return {
    projectId: parsed.project_id,
    clientEmail: parsed.client_email,
    // 일부 환경에서 \n 이 escape 된 채 들어오면 실제 줄바꿈으로 복원
    privateKey: (parsed.private_key || "").replace(/\\n/g, "\n"),
  };
}

export function getDb(): Firestore {
  if (_db) return _db;
  let app: App;
  const existing = getApps();
  if (existing.length > 0) {
    app = existing[0];
  } else {
    app = initializeApp({ credential: cert(loadServiceAccount()) });
  }
  // named DB(예: "default") 지원. 미지정이면 (default).
  const dbId = process.env.FIREBASE_DATABASE_ID;
  _db = dbId ? getFirestore(app, dbId) : getFirestore(app);
  return _db;
}
