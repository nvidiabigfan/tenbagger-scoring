"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

export default function NavAuth() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setUser(data.session?.user ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) =>
      setUser(session?.user ?? null)
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!user) {
    return (
      <Link href="/login" className="text-sm text-gray-500 hover:text-gray-900">
        로그인
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-4">
      <Link href="/watchlist" className="text-sm text-gray-500 hover:text-gray-900">
        워치리스트
      </Link>
      <button
        onClick={() => supabase.auth.signOut()}
        className="text-sm text-gray-400 hover:text-red-500"
      >
        로그아웃
      </button>
    </div>
  );
}
