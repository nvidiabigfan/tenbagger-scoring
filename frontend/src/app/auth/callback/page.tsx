"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    // Supabase가 URL 해시에서 세션 토큰을 자동으로 처리
    supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        router.replace("/");
      }
    });
  }, [router]);

  return (
    <div className="flex flex-col items-center pt-24 text-center">
      <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
      <p className="text-gray-500 text-sm">로그인 처리 중...</p>
    </div>
  );
}
