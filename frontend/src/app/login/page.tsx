"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendLink = async () => {
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    const { error: err } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: `${location.origin}/auth/callback` },
    });
    setLoading(false);
    if (err) {
      setError(err.message);
    } else {
      setSent(true);
    }
  };

  if (sent) {
    return (
      <div className="flex flex-col items-center pt-24 text-center">
        <div className="text-4xl mb-4">📬</div>
        <h1 className="text-xl font-bold text-gray-900 mb-2">이메일을 확인하세요</h1>
        <p className="text-gray-500 text-sm mb-1">
          <span className="font-semibold">{email}</span>로 로그인 링크를 보냈습니다.
        </p>
        <p className="text-gray-400 text-xs">링크를 클릭하면 자동으로 로그인됩니다.</p>
        <button
          onClick={() => router.push("/")}
          className="mt-8 text-sm text-blue-600 hover:underline"
        >
          ← 홈으로
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center pt-24">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-1 text-center">로그인</h1>
        <p className="text-gray-400 text-xs text-center mb-6">이메일로 Magic Link를 보내드립니다</p>

        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendLink()}
          placeholder="이메일 주소"
          className="w-full px-4 py-3 text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 mb-3"
          autoComplete="email"
        />

        {error && <p className="text-red-500 text-xs mb-3">{error}</p>}

        <button
          onClick={sendLink}
          disabled={loading || !email.trim()}
          className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium text-sm hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "전송 중..." : "링크 받기"}
        </button>
      </div>
    </div>
  );
}
