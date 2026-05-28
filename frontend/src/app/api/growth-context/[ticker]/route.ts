import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await params;
  const t = ticker.toUpperCase();

  try {
    // 이 종목 최근 12주 히스토리
    const { data: history } = await supabase
      .from("score_history")
      .select("week_date, total_score")
      .eq("ticker", t)
      .order("week_date", { ascending: false })
      .limit(12);

    if (!history || history.length === 0) {
      return NextResponse.json({ available: false });
    }

    const currentScore = history[0].total_score;
    const latestWeek = history[0].week_date;

    // 같은 주차 전 종목 점수 → 분위수
    const { data: allWeek } = await supabase
      .from("score_history")
      .select("total_score")
      .eq("week_date", latestWeek);

    const allScores = (allWeek ?? []).map((r) => Number(r.total_score));
    const below = allScores.filter((s) => s < currentScore).length;
    const topPct = Math.max(1, Math.round(((allScores.length - below) / allScores.length) * 100));

    const delta =
      history.length >= 2
        ? Math.round((currentScore - Number(history[1].total_score)) * 10) / 10
        : null;

    return NextResponse.json({
      available: true,
      ticker: t,
      currentScore,
      topPct,
      universeSize: allScores.length,
      delta,
      history: [...history].reverse().map((h) => ({
        week_date: h.week_date,
        total_score: Number(h.total_score),
      })),
    });
  } catch (e) {
    return NextResponse.json({ available: false, error: String(e) });
  }
}
