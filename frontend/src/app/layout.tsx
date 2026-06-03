import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import NavAuth from "@/components/NavAuth";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "텐배거스코어링",
  description: "미국주식 텐배거 후보 가능성 0~100점 스코어링",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className={`${inter.className} bg-gray-50 min-h-screen`}>
        <nav className="bg-white border-b border-gray-200 px-4 py-3">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <Link href="/" className="text-lg font-bold text-gray-900 hover:text-blue-600">
              텐배거스코어링
            </Link>
            <div className="flex items-center gap-4">
              <Link href="/ranking" className="text-sm text-gray-500 hover:text-gray-900">
                랭킹보드
              </Link>
              <Link href="/congress" className="text-sm text-gray-500 hover:text-gray-900">
                의회매매
              </Link>
              <NavAuth />
            </div>
          </div>
        </nav>
        <main className="max-w-4xl mx-auto px-4 py-8">{children}</main>
        <footer className="text-center text-xs text-gray-400 py-8">
          본 서비스는 투자 자문이 아니며 참고용입니다.
        </footer>
      </body>
    </html>
  );
}
