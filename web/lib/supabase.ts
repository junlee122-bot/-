import { createClient } from "@supabase/supabase-js";

// 서버 전용 Supabase 클라이언트.
// service_role 키는 서버 컴포넌트/Route Handler 에서만 사용하며 클라이언트로
// 절대 노출되지 않는다 (NEXT_PUBLIC_ 접두어를 쓰지 않음).
export function getServerSupabase() {
  const url = process.env.SUPABASE_URL;
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;

  if (!url || !key) {
    throw new Error(
      "Supabase 미설정: SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY 환경변수를 설정하세요."
    );
  }

  return createClient(url, key, {
    auth: { persistSession: false },
  });
}
