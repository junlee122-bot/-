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

function loadServiceAccount(): ServiceAccount {
  const b64 = process.env.FIREBASE_SERVICE_ACCOUNT_BASE64;
  const raw = b64
    ? Buffer.from(b64, "base64").toString("utf-8")
    : process.env.FIREBASE_SERVICE_ACCOUNT;
  if (!raw) {
    throw new Error(
      "Firebase 미설정: FIREBASE_SERVICE_ACCOUNT(JSON) 또는 " +
        "FIREBASE_SERVICE_ACCOUNT_BASE64 환경변수를 설정하세요."
    );
  }
  const parsed = JSON.parse(raw);
  return {
    projectId: parsed.project_id,
    clientEmail: parsed.client_email,
    privateKey: parsed.private_key,
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
  _db = getFirestore(app);
  return _db;
}
