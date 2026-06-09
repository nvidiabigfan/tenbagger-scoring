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
  score: number | null;
  analyzed_at: string | null;
}

function scoreSignal(score: number): { label: string; cls: string } {
  if (score >= 75) return { label: "강한 주목", cls: "bg-green-100 text-green-700" };
  if (score >= 55) return { label: "긍정 시그널", cls: "bg-blue-100 text-blue-600" };
  if (score >= 35) return { label: "중립", cls: "bg-yellow-100 text-yellow-600" };
  return { label: "부정 시그널", cls: "bg-red-100 text-red-500" };
}

function scoreBarCls(score: number): string {
  if (score >= 80) return "bg-green-400";
  if (score >= 60) return "bg-blue-400";
  if (score >= 40) return "bg-yellow-400";
  return "bg-red-400";
}

function scoreTextCls(score: number): string {
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-blue-600";
  if (score >= 40) return "text-yellow-500";
  return "text-red-500";
}

export default function WatchlistPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [addTicker, setAddTicker] = useState("");
  const [addError, setAddError] = useState("");
  const [adding, setAdding] = useState(false);

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

      const watchRows = (rows as unknown as Omit<WatchItem, "score" | "analyzed_at">[]) ?? [];

      // 점수 조회
      let scoreMap: Record<string, { score: number; analyzed_at: string }> = {};
      if (watchRows.length > 0) {
        const tickers = watchRows.map((r) => r.ticker);
        const { data: analysisRows } = await supabase
          .from("analysis_results")
          .select("ticker, total_score, analyzed_at")
          .in("ticker", tickers)
          .order("analyzed_at", { ascending: false })
          .limit(tickers.length * 3);

        for (const ar of (analysisRows ?? [])) {
          if (!scoreMap[ar.ticker]) {
            scoreMap[ar.ticker] = { score: ar.total_score, analyzed_at: ar.analyzed_at };
          }
        }
      }

      // 점수 병합 후 내림차순 정렬
      const merged: WatchItem[] = watchRows.map((r) => ({
        ...r,
        score: scoreMap[r.ticker]?.score ?? null,
        analyzed_at: scoreMap[r.ticker]?.analyzed_at ?? null,
      }));
      merged.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));

      setItems(merged);
      setLoading(false);
    });
  }, []);

  const remove = async (ticker: string) => {
    if (!user) return;
    await supabase.from("watchlist").delete().eq("ticker", ticker).eq("user_id", user.id);
    setItems((prev) => prev.filter((i) => i.ticker !== ticker));
  };

  const add = async () => {
    const t = addTicker.trim().toUpperCase();
    if (!/^[A-Z.]{1,5}$/.test(t)) {
      setAddError("티커는 영문 대문자 1~5자 (예: AAPL, BRK.B)");
      return;
    }
    if (items.some((i) => i.ticker === t)) {
      setAddError("이미 워치리스트에 있습니다.");
      return;
    }
    setAdding(true);
    setAddError("");
    const { error } = await supabase.from("watchlist").upsert(
      { user_id: user!.id, ticker: t, alert_enabled: true, alert_threshold: 10.0 },
      { onConflict: "user_id,ticker" }
    );
    if (error) {
      setAddError("추가 실패: " + error.message);
      setAdding(false);
      return;
    }
    setItems((prev) => [
      { ticker: t, added_at: new Date().toISOString(), alert_enabled: true, stocks: null, score: null, analyzed_at: null },
      ...prev,
    ]);
    setAddTicker("");
    setAdding(false);
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
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">내 워치리스트</h1>
          <p className="text-xs text-gray-400 mt-0.5">점수 높은 순 정렬</p>
        </div>
        <span className="text-sm text-gray-400">{items.length}개 종목</span>
      </div>

      {/* 티커 추가 폼 */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm px-4 py-3 mb-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={addTicker}
            onChange={(e) => { setAddTicker(e.target.value.toUpperCase()); setAddError(""); }}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="티커 입력 (예: AAPL)"
            maxLength={5}
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono uppercase focus:outline-none focus:border-blue-400"
          />
          <button
            onClick={add}
            disabled={adding || !addTicker.trim()}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {adding ? "추가 중…" : "추가"}
          </button>
        </div>
        {addError && <p className="text-xs text-red-500 mt-1.5">{addError}</p>}
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
        <>
          {/* 상위 3 카드 */}
          {items.length >= 1 && (
            <div className={`grid gap-2 sm:gap-3 mb-6 ${items.length >= 3 ? "grid-cols-3" : items.length === 2 ? "grid-cols-2" : "grid-cols-1"}`}>
              {items.slice(0, 3).map((item, idx) => {
                const score = item.score ?? 0;
                const sig = scoreSignal(score);
                const medals = ["🥇", "🥈", "🥉"];
                return (
                  <div key={item.ticker} className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 sm:p-4 hover:border-blue-200 hover:shadow-md transition-all text-center">
                    <div className="mb-1">
                      <span className="text-base">{medals[idx]}</span>
                    </div>
                    <Link href={`/analyze/${item.ticker}`} className="font-bold text-lg text-blue-600 hover:underline block">
                      {item.ticker}
                    </Link>
                    <div className="text-xs text-gray-400 truncate">{item.stocks?.company_name ?? "-"}</div>
                    {item.score !== null ? (
                      <>
                        <div className={`text-2xl font-black tabular-nums my-1.5 ${scoreTextCls(score)}`}>
                          {score}
                        </div>
                        <div className="h-1 bg-gray-100 rounded-full overflow-hidden mb-1.5">
                          <div className={`h-full rounded-full ${scoreBarCls(score)}`} style={{ width: `${score}%` }} />
                        </div>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${sig.cls}`}>
                          {sig.label}
                        </span>
                      </>
                    ) : (
                      <div className="text-xs text-gray-300 my-2">미분석</div>
                    )}
                    <div className="mt-2 flex justify-center">
                      <button
                        onClick={() => remove(item.ticker)}
                        className="text-gray-300 hover:text-red-400 transition-colors text-sm"
                        title="삭제"
                      >
                        ☆ 제거
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* 전체 테이블 */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium w-10">#</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium w-16">티커</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium">회사명</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">섹터</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium">점수</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">시그널</th>
                  <th className="px-4 py-3 text-right text-gray-500 font-medium hidden sm:table-cell">추가일</th>
                  <th className="px-4 py-3 w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {items.map((item, idx) => {
                  const score = item.score ?? 0;
                  const sig = scoreSignal(score);
                  return (
                    <tr key={item.ticker} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5 text-gray-400 tabular-nums text-sm">{idx + 1}</td>
                      <td className="px-4 py-2.5 font-semibold">
                        <Link href={`/analyze/${item.ticker}`} className="text-blue-600 hover:underline">
                          {item.ticker}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5 text-gray-500 truncate max-w-36">
                        {item.stocks?.company_name ?? "-"}
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs truncate max-w-28 hidden sm:table-cell">
                        {item.stocks?.sector ?? "-"}
                      </td>
                      <td className="px-4 py-2.5">
                        {item.score !== null ? (
                          <div className="flex items-center gap-2">
                            <span className={`font-bold tabular-nums text-sm ${scoreTextCls(score)}`}>
                              {score}
                            </span>
                            <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${scoreBarCls(score)}`}
                                style={{ width: `${score}%` }}
                              />
                            </div>
                          </div>
                        ) : (
                          <span className="text-gray-300 text-xs">미분석</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 hidden sm:table-cell">
                        {item.score !== null && (
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sig.cls}`}>
                            {sig.label}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums text-xs hidden sm:table-cell">
                        {new Date(item.added_at).toLocaleDateString("ko-KR")}
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        <button
                          onClick={() => remove(item.ticker)}
                          className="text-gray-300 hover:text-red-400 transition-colors text-base leading-none"
                          title="삭제"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="text-center text-xs text-gray-300 mt-6">
            본 서비스는 투자 자문이 아니며 참고용입니다.
          </p>
        </>
      )}
    </div>
  );
}
