"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

interface WatchItem {
  ticker: string;
  added_at: string;
  alert_enabled: boolean;
  stocks: { company_name: string; sector: string } | null;
}

export default function WatchlistPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      const u = data.session?.user ?? null;
      setUser(u);
      if (!u) {
        setLoading(false);
        return;
      }
      const { data: rows } = await supabase
        .from("watchlist")
        .select("ticker, added_at, alert_enabled, stocks(company_name, sector)")
        .eq("user_id", u.id)
        .order("added_at", { ascending: false });
      setItems((rows as unknown as WatchItem[]) ?? []);
      setLoading(false);
    });
  }, []);

  const remove = async (ticker: string) => {
    await supabase.from("watchlist").delete().eq("ticker", ticker);
    setItems((prev) => prev.filter((i) => i.ticker !== ticker));
  };

  if (loading) {
    return (
      <div className="flex justify-center pt-20">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex flex-col items-center pt-24 text-center">
        <p className="text-gray-500 mb-4">워치리스트를 사용하려면 로그인이 필요합니다.</p>
        <Link href="/login" className="px-6 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700">
          로그인
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">내 워치리스트</h1>
        <span className="text-sm text-gray-400">{items.length}개 종목</span>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
          <p className="text-gray-400 mb-4">아직 추가된 종목이 없습니다.</p>
          <button
            onClick={() => router.push("/")}
            className="text-blue-600 text-sm hover:underline"
          >
            종목 검색하기 →
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="px-4 py-3 text-left text-gray-500 font-medium">티커</th>
                <th className="px-4 py-3 text-left text-gray-500 font-medium">회사명</th>
                <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">섹터</th>
                <th className="px-4 py-3 text-right text-gray-500 font-medium">추가일</th>
                <th className="px-4 py-3 w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {items.map((item) => (
                <tr key={item.ticker} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-semibold">
                    <Link href={`/analyze/${item.ticker}`} className="text-blue-600 hover:underline">
                      {item.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600 truncate max-w-36">
                    {item.stocks?.company_name ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs hidden sm:table-cell">
                    {item.stocks?.sector ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-400 tabular-nums text-xs">
                    {new Date(item.added_at).toLocaleDateString("ko-KR")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => remove(item.ticker)}
                      className="text-gray-300 hover:text-red-400 transition-colors text-base leading-none"
                      title="삭제"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
