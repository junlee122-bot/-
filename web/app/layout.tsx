import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Betman Value Analyzer",
  description:
    "베트맨 전용 베팅 가치 분석 — Pinnacle 기준 공정확률 대비 상대적으로 덜 불리한 픽 줄세우기",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
