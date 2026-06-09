import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL/SUPABASE_SERVICE_KEY env not configured");
  return createClient(url, key);
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { ticker: string } }
) {
  const ticker = params.ticker.toUpperCase().replace(/[^A-Z.]/g, "").slice(0, 6);
  if (!ticker) return NextResponse.json({ error: "invalid ticker" }, { status: 400 });

  const sb = getServiceClient();

  try {
    // 기존 debates 테이블 (최종 bull/bear 텍스트)
    const { data: debate, error: debateErr } = await sb
      .from("debates")
      .select("ticker, bull_text, bear_text, score_at_gen, signal_at_gen, generated_at")
      .eq("ticker", ticker)
      .maybeSingle();
    if (debateErr) throw debateErr;
    if (!debate) return NextResponse.json({ available: false });

    // 멀티에이전트 세션: 최신 completed 1건 (테이블 없을 경우 graceful)
    let session: { id: string; score_at_gen: number; signal_at_gen: string; created_at: string } | null = null;
    let rounds: { round_no: number; bull_text: string; bear_text: string }[] = [];
    let verdict: { bull_score: number; bear_score: number; recommendation: string; verdict_text: string } | null = null;

    try {
      const { data: sessionData } = await sb
        .from("debate_sessions")
        .select("id, score_at_gen, signal_at_gen, created_at")
        .eq("ticker", ticker)
        .eq("status", "completed")
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();

      if (sessionData) {
        session = sessionData;

        const { data: roundsData } = await sb
          .from("debate_rounds")
          .select("round_no, bull_text, bear_text")
          .eq("session_id", sessionData.id)
          .order("round_no", { ascending: true });
        rounds = roundsData ?? [];

        const { data: verdictData } = await sb
          .from("debate_verdicts")
          .select("bull_score, bear_score, recommendation, verdict_text")
          .eq("session_id", sessionData.id)
          .maybeSingle();
        verdict = verdictData ?? null;
      }
    } catch {
      // debate_sessions 테이블 미생성 시 graceful — 기존 debates 데이터만 반환
    }

    return NextResponse.json({
      available: true,
      ...debate,
      session,
      rounds,
      verdict,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
