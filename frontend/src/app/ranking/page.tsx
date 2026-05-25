import Link from "next/link";
import { supabase } from "@/lib/supabase";

export const revalidate = 3600;

interface RankRow {
  rank: number;
  ticker: string;
  score: number;
  rank_change: number | null;
  stocks: { company_name: string } | null;
}

export default async function RankingPage() {
  const today = new Date().toISOString().split("T")[0];
  const { data } = await supabase
    .from("ranking_snapshots")
    .select("rank, ticker, score, rank_change, stocks(company_name)")
    .eq("date", today)
    .order("rank", { ascending: true });

  const rows = (data ?? []) as unknown as RankRow[];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">스코어 상위 100</h1>
        <span className="text-sm text-gray-400">{today} 기준</span>
      </div>

      {rows.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
          <p className="text-gray-400 mb-2">오늘의 랭킹 데이터가 아직 없습니다.</p>
          <p className="text-gray-300 text-sm">일일 배치 작업(평일 KST 21:00) 후 갱신됩니다.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="px-4 py-3 text-left text-gray-500 font-medium w-12">순위</th>
                <th className="px-4 py-3 text-left text-gray-500 font-medium">티커</th>
                <th className="px-4 py-3 text-left text-gray-500 font-medium">회사명</th>
                <th className="px-4 py-3 text-right text-gray-500 font-medium">점수</th>
                <th className="px-4 py-3 text-right text-gray-500 font-medium">변동</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.map((row) => (
                <tr key={row.rank} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-400 tabular-nums">{row.rank}</td>
                  <td className="px-4 py-3 font-semibold">
                    <Link href={`/analyze/${row.ticker}`} className="text-blue-600 hover:underline">
                      {row.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-40">
                    {row.stocks?.company_name ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-right font-bold tabular-nums">{row.score}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {row.rank_change === null ? (
                      <span className="text-gray-300">-</span>
                    ) : row.rank_change > 0 ? (
                      <span className="text-green-600">▲{row.rank_change}</span>
                    ) : row.rank_change < 0 ? (
                      <span className="text-red-500">▼{Math.abs(row.rank_change)}</span>
                    ) : (
                      <span className="text-gray-300">-</span>
                    )}
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
