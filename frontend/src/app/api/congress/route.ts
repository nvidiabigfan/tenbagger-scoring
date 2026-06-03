import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export const revalidate = 3600;

export async function GET() {
  try {
    // ① 의원 수익률 리더보드 (최소 8거래, 최근 365일)
    const { data: leaderboard, error: lbErr } = await supabase.rpc(
      "congress_leaderboard",
      { min_trades: 8, since_days: 365 }
    );
    if (lbErr) throw lbErr;

    // ② 티커별 최근 의회 순매수 (최근 90일)
    const { data: netbuyRaw, error: nbErr } = await supabase.rpc(
      "congress_netbuy",
      { since_days: 90 }
    );
    if (nbErr) throw nbErr;

    const netbuy = (netbuyRaw ?? []).filter((r: { net: number }) => r.net > 0).slice(0, 30);

    // 순매수 티커 회사명 보강
    const tickers = netbuy.map((r: { ticker: string }) => r.ticker);
    const nameMap: Record<string, string> = {};
    if (tickers.length > 0) {
      const { data: stocks } = await supabase
        .from("stocks")
        .select("ticker, company_name")
        .in("ticker", tickers);
      for (const s of stocks ?? []) nameMap[s.ticker] = s.company_name;
    }

    // ③ 최근 공시 거래 20건
    const { data: recent } = await supabase
      .from("congress_trades")
      .select(
        "ticker, representative, party, house, transaction, side, transaction_date, report_date, range_text, excess_return"
      )
      .order("report_date", { ascending: false })
      .limit(20);

    // 데이터 최신성
    const { data: latest } = await supabase
      .from("congress_trades")
      .select("snapshot_date")
      .order("snapshot_date", { ascending: false })
      .limit(1)
      .maybeSingle();

    return NextResponse.json({
      available: (leaderboard ?? []).length > 0 || (recent ?? []).length > 0,
      snapshotDate: latest?.snapshot_date ?? null,
      leaderboard: (leaderboard ?? []).slice(0, 10),
      leaderboardBottom: (leaderboard ?? []).slice(-5).reverse(),
      netbuy: netbuy.map((r: { ticker: string; buys: number; sells: number; net: number; reps: number }) => ({
        ...r,
        company_name: nameMap[r.ticker] ?? null,
      })),
      recent: recent ?? [],
    });
  } catch (e) {
    return NextResponse.json({ available: false, error: String(e) }, { status: 200 });
  }
}
