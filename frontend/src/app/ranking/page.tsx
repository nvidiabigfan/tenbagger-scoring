import Link from "next/link";
import { supabase } from "@/lib/supabase";
import WatchlistButton from "@/components/WatchlistButton";

export const revalidate = 3600;

interface RankRow {
  rank: number;
  ticker: string;
  score: number;
  rank_change: number | null;
  stocks: { company_name: string; sector: string } | null;
}

function stalenessInfo(analyzedAt: string | undefined): { label: string; cls: string } | null {
  if (!analyzedAt) return null;
  const diffDays = (Date.now() - new Date(analyzedAt).getTime()) / 86400000;
  if (diffDays < 1) return null; // 오늘 분석 — 표시 불필요
  if (diffDays < 3) return { label: `${Math.floor(diffDays)}일 전`, cls: "text-gray-300" };
  return { label: `${Math.floor(diffDays)}일 전`, cls: "text-orange-400 font-medium" };
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

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) return <span className="text-base" title="1위">🥇</span>;
  if (rank === 2) return <span className="text-base" title="2위">🥈</span>;
  if (rank === 3) return <span className="text-base" title="3위">🥉</span>;
  return <span className="text-gray-400 tabular-nums text-sm">{rank}</span>;
}

export default async function RankingPage() {
  // 가장 최근 snapshot 날짜 먼저 조회
  const { data: latestRow } = await supabase
    .from("ranking_snapshots")
    .select("date")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();

  const latestDate = latestRow?.date ?? new Date().toISOString().split("T")[0];

  const { data } = await supabase
    .from("ranking_snapshots")
    .select("rank, ticker, score, rank_change, stocks(company_name, sector)")
    .eq("date", latestDate)
    .order("rank", { ascending: true });

  const rows = (data ?? []) as unknown as RankRow[];

  // 각 ticker의 최신 분석일 조회 (stale 표시용)
  const tickerList = rows.map((r) => r.ticker);
  const { data: analysisRows } = tickerList.length > 0
    ? await supabase
        .from("analysis_results")
        .select("ticker, analyzed_at")
        .in("ticker", tickerList)
        .order("analyzed_at", { ascending: false })
        .limit(tickerList.length * 3)
    : { data: [] };

  const analyzedAtMap: Record<string, string> = {};
  for (const ar of (analysisRows ?? [])) {
    if (!analyzedAtMap[ar.ticker]) analyzedAtMap[ar.ticker] = ar.analyzed_at;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">스코어 상위 100</h1>
          <p className="text-xs text-gray-400 mt-0.5">텐배거 가능성 점수 기준 (0~100점)</p>
        </div>
        <span className="text-sm text-gray-400">{latestDate} 기준</span>
      </div>

      {rows.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
          <p className="text-gray-400 mb-2">오늘의 랭킹 데이터가 아직 없습니다.</p>
          <p className="text-gray-300 text-sm">일일 배치 작업(평일 KST 21:00) 후 갱신됩니다.</p>
        </div>
      ) : (
        <>
          {/* 상위 3 카드 */}
          <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-6">
            {rows.slice(0, 3).map((row) => {
              const sig = scoreSignal(row.score);
              return (
                <Link
                  key={row.rank}
                  href={`/analyze/${row.ticker}`}
                  className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 sm:p-4 hover:border-blue-200 hover:shadow-md transition-all text-center"
                >
                  <div className="mb-1">
                    <RankBadge rank={row.rank} />
                  </div>
                  <div className="font-bold text-lg text-blue-600">{row.ticker}</div>
                  <div className="text-xs text-gray-400 truncate">{row.stocks?.company_name ?? "-"}</div>
                  <div className={`text-2xl font-black tabular-nums my-1.5 ${scoreTextCls(row.score)}`}>
                    {row.score}
                  </div>
                  <div className="h-1 bg-gray-100 rounded-full overflow-hidden mb-1.5">
                    <div className={`h-full rounded-full ${scoreBarCls(row.score)}`} style={{ width: `${row.score}%` }} />
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${sig.cls}`}>
                    {sig.label}
                  </span>
                  <div className="mt-2 flex justify-center">
                    <WatchlistButton ticker={row.ticker} />
                  </div>
                </Link>
              );
            })}
          </div>

          {/* 전체 테이블 */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium w-10">순위</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium w-16">티커</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium">회사명</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">섹터</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium">점수</th>
                  <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">시그널</th>
                  <th className="px-4 py-3 text-right text-gray-500 font-medium w-14">변동</th>
                  <th className="px-4 py-3 text-right text-gray-500 font-medium w-16 hidden sm:table-cell">분석일</th>
                  <th className="px-4 py-3 w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.map((row) => {
                  const sig = scoreSignal(row.score);
                  return (
                    <tr key={row.rank} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5">
                        <RankBadge rank={row.rank} />
                      </td>
                      <td className="px-4 py-2.5 font-semibold">
                        <Link href={`/analyze/${row.ticker}`} className="text-blue-600 hover:underline">
                          {row.ticker}
                        </Link>
                      </td>

                      <td className="px-4 py-2.5 text-gray-500 truncate max-w-36">
                        {row.stocks?.company_name ?? "-"}
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs truncate max-w-28 hidden sm:table-cell">
                        {row.stocks?.sector ?? "-"}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className={`font-bold tabular-nums text-sm ${scoreTextCls(row.score)}`}>
                            {row.score}
                          </span>
                          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${scoreBarCls(row.score)}`}
                              style={{ width: `${row.score}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 hidden sm:table-cell">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sig.cls}`}>
                          {sig.label}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-sm">
                        {row.rank_change === null ? (
                          <span className="text-gray-300 text-xs">신규</span>
                        ) : row.rank_change > 0 ? (
                          <span className="text-green-600">▲{row.rank_change}</span>
                        ) : row.rank_change < 0 ? (
                          <span className="text-red-500">▼{Math.abs(row.rank_change)}</span>
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right hidden sm:table-cell">
                        {(() => {
                          const info = stalenessInfo(analyzedAtMap[row.ticker]);
                          if (!info) return <span className="text-gray-300 text-xs">오늘</span>;
                          return <span className={`text-xs ${info.cls}`}>{info.label}</span>;
                        })()}
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        <WatchlistButton ticker={row.ticker} />
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
