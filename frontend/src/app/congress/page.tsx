"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import WatchlistButton from "@/components/WatchlistButton";

interface LeaderRow {
  representative: string;
  party: string | null;
  house: string | null;
  avg_excess_return: number;
  avg_price_change: number;
  trade_count: number;
}
interface NetbuyRow {
  ticker: string;
  buys: number;
  sells: number;
  net: number;
  reps: number;
  company_name: string | null;
}
interface RecentRow {
  ticker: string;
  representative: string;
  party: string | null;
  house: string | null;
  transaction: string | null;
  side: string | null;
  transaction_date: string | null;
  report_date: string | null;
  range_text: string | null;
  excess_return: number | null;
}
interface CongressData {
  available: boolean;
  snapshotDate: string | null;
  leaderboard: LeaderRow[];
  leaderboardBottom: LeaderRow[];
  netbuy: NetbuyRow[];
  recent: RecentRow[];
  error?: string;
}

function partyCls(p: string | null): string {
  if (p === "D") return "bg-blue-100 text-blue-600";
  if (p === "R") return "bg-red-100 text-red-500";
  return "bg-gray-100 text-gray-500";
}
function pct(v: number | null): string {
  if (v === null || v === undefined) return "-";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function pctCls(v: number | null): string {
  if (v === null || v === undefined) return "text-gray-400";
  return v >= 0 ? "text-green-600" : "text-red-500";
}
function MedalRank({ i }: { i: number }) {
  if (i === 0) return <span title="1위">🥇</span>;
  if (i === 1) return <span title="2위">🥈</span>;
  if (i === 2) return <span title="3위">🥉</span>;
  return <span className="text-gray-400 tabular-nums text-sm">{i + 1}</span>;
}

export default function CongressPage() {
  const [data, setData] = useState<CongressData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/congress")
      .then((r) => r.json())
      .then((d) => setData(d))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="mb-2">
        <h1 className="text-2xl font-bold text-gray-900">의회 매매 트래커</h1>
        <p className="text-xs text-gray-400 mt-0.5">
          미 상·하원 의원 주식 매매 공시 (STOCK Act) · 출처 Quiver Quantitative
          {data?.snapshotDate ? ` · ${data.snapshotDate} 기준` : ""}
        </p>
      </div>

      <div className="bg-amber-50 border border-amber-100 rounded-xl px-4 py-2.5 mb-6">
        <p className="text-xs text-amber-700">
          ⚠️ 거래일로부터 공시까지 평균 약 24일 지연되는 <b>후행 정보</b>입니다.
          매수 권유가 아니며, 정성적 참고 지표로만 활용하세요.
        </p>
      </div>

      {loading ? (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center text-gray-400">
          불러오는 중…
        </div>
      ) : !data?.available ? (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
          <p className="text-gray-400 mb-2">아직 수집된 의회 매매 데이터가 없습니다.</p>
          <p className="text-gray-300 text-sm">일일 배치(평일 KST 03:00) 후 갱신됩니다.</p>
        </div>
      ) : (
        <>
          {/* 섹션 1: 수익률 리더보드 */}
          <section className="mb-8">
            <h2 className="text-base font-bold text-gray-800 mb-1">
              의원 수익률 탑10
            </h2>
            <p className="text-xs text-gray-400 mb-3">
              SPY 대비 평균 초과수익 기준 (최근 1년·최소 8거래)
            </p>
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium w-10">순위</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium">의원</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell w-16">소속</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">초과수익</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium hidden sm:table-cell">종목수익</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium w-16">거래수</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.leaderboard.map((r, i) => (
                    <tr key={r.representative} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5"><MedalRank i={i} /></td>
                      <td className="px-4 py-2.5 font-semibold text-gray-900">{r.representative}</td>
                      <td className="px-4 py-2.5 hidden sm:table-cell">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${partyCls(r.party)}`}>
                          {r.party ?? "?"} · {r.house === "Senate" ? "상원" : "하원"}
                        </span>
                      </td>
                      <td className={`px-4 py-2.5 text-right font-bold tabular-nums ${pctCls(r.avg_excess_return)}`}>
                        {pct(r.avg_excess_return)}
                      </td>
                      <td className={`px-4 py-2.5 text-right tabular-nums hidden sm:table-cell ${pctCls(r.avg_price_change)}`}>
                        {pct(r.avg_price_change)}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums">{r.trade_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* 섹션 2: 티커별 의회 순매수 */}
          <section className="mb-8">
            <h2 className="text-base font-bold text-gray-800 mb-1">최근 의회 순매수 종목</h2>
            <p className="text-xs text-gray-400 mb-3">최근 90일 매수−매도 건수 기준 · 종목 클릭 시 상세 점수로 이동</p>
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium w-16">티커</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">회사명</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">순매수</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium hidden sm:table-cell">매수/매도</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium w-16">의원수</th>
                    <th className="px-4 py-3 w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.netbuy.length === 0 ? (
                    <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-300">순매수 종목 없음</td></tr>
                  ) : data.netbuy.map((r) => (
                    <tr key={r.ticker} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5 font-semibold">
                        <Link href={`/analyze/${r.ticker}`} className="text-blue-600 hover:underline">{r.ticker}</Link>
                      </td>
                      <td className="px-4 py-2.5 text-gray-500 truncate max-w-40 hidden sm:table-cell">{r.company_name ?? "-"}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-green-600 tabular-nums">+{r.net}</td>
                      <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums hidden sm:table-cell">{r.buys}/{r.sells}</td>
                      <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums">{r.reps}</td>
                      <td className="px-2 py-2.5 text-center"><WatchlistButton ticker={r.ticker} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* 섹션 3: 최근 공시 거래 */}
          <section>
            <h2 className="text-base font-bold text-gray-800 mb-3">최근 공시 거래</h2>
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium">의원</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium w-16">티커</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium w-16">구분</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium hidden sm:table-cell">규모</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium hidden sm:table-cell">거래일</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.recent.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5 text-gray-700 truncate max-w-36">{r.representative}</td>
                      <td className="px-4 py-2.5 font-semibold">
                        <Link href={`/analyze/${r.ticker}`} className="text-blue-600 hover:underline">{r.ticker}</Link>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${r.side === "buy" ? "bg-green-100 text-green-700" : r.side === "sell" ? "bg-red-100 text-red-500" : "bg-gray-100 text-gray-500"}`}>
                          {r.side === "buy" ? "매수" : r.side === "sell" ? "매도" : "기타"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs hidden sm:table-cell">{r.range_text ?? "-"}</td>
                      <td className="px-4 py-2.5 text-right text-gray-400 text-xs tabular-nums hidden sm:table-cell">{r.transaction_date ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className="text-center text-xs text-gray-300 mt-8">
            본 서비스는 투자 자문이 아니며 참고용입니다.
          </p>
        </>
      )}
    </div>
  );
}
