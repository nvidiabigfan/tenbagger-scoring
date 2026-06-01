import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const MAX_MSG_LEN = 1000;
const MAX_MESSAGES = 20;

function getSupplySupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL/SUPABASE_SERVICE_KEY env not configured");
  return createClient(url, key);
}

async function buildContext(question: string): Promise<string> {
  const sb = getSupplySupabase();
  const parts: string[] = [];

  const matched = question.match(/\b[A-Z]{2,5}\b/g) ?? [];
  const tickers = Array.from(new Set(matched)).slice(0, 3);

  if (tickers.length === 0) {
    const { data: snaps } = await sb
      .from("supply_snapshots")
      .select("ticker, snapshot_date, close_price, short_interest_pct, volume_vs_avg, institutional_net")
      .order("snapshot_date", { ascending: false })
      .limit(10);
    if (snaps?.length) {
      parts.push("=== 최근 수급 스냅샷 ===");
      parts.push(
        snaps.map((s) =>
          `${s.ticker}: 종가 $${s.close_price?.toFixed(2) ?? "N/A"}, 공매도 ${s.short_interest_pct?.toFixed(1) ?? "N/A"}%, 거래량배수 ${s.volume_vs_avg?.toFixed(2) ?? "N/A"}x, 기관순매수 $${((s.institutional_net ?? 0) / 1e6).toFixed(1)}M (${s.snapshot_date})`
        ).join("\n")
      );
    }
    return parts.join("\n");
  }

  for (const ticker of tickers) {
    const [{ data: snaps }, { data: analysis }, { data: sec }] = await Promise.all([
      sb.from("supply_snapshots")
        .select("snapshot_date, close_price, short_interest_pct, pc_ratio, volume_vs_avg, institutional_net, insider_net")
        .eq("ticker", ticker)
        .order("snapshot_date", { ascending: false })
        .limit(5),
      sb.from("analysis_results")
        .select("total_score, signal, confidence, module_scores, evidence, analyzed_at")
        .eq("ticker", ticker)
        .order("analyzed_at", { ascending: false })
        .limit(1),
      sb.from("sec_filings")
        .select("form_type, filed_date, ai_summary, risk_flags")
        .eq("ticker", ticker)
        .eq("analyzed", true)
        .order("filed_date", { ascending: false })
        .limit(2),
    ]);

    if (snaps?.length) {
      parts.push(`\n=== ${ticker} 수급 데이터 (최근 ${snaps.length}일) ===`);
      parts.push(
        snaps.map((s) =>
          `${s.snapshot_date}: 종가 $${s.close_price?.toFixed(2) ?? "N/A"}, 공매도 ${s.short_interest_pct?.toFixed(1) ?? "N/A"}%, 거래량배수 ${s.volume_vs_avg?.toFixed(2) ?? "N/A"}x, P/C ${s.pc_ratio?.toFixed(2) ?? "N/A"}, 기관 $${((s.institutional_net ?? 0) / 1e6).toFixed(1)}M, 내부자 $${((s.insider_net ?? 0) / 1e6).toFixed(1)}M`
        ).join("\n")
      );
    }

    if (analysis?.[0]) {
      const a = analysis[0];
      parts.push(`\n=== ${ticker} 성장 스코어링 (${a.analyzed_at?.slice(0, 10)}) ===`);
      parts.push(`총점: ${a.total_score?.toFixed(1)}점 / 신호: ${a.signal} / 신뢰도: ${((a.confidence ?? 0) * 100).toFixed(0)}%`);

      const ms = a.module_scores as Record<string, { score: number; signal: string }> | null;
      if (ms) {
        const moduleNames: Record<string, string> = {
          revenue: "매출성장", etf: "ETF흐름", analyst: "애널리스트",
          size: "시가총액", momentum: "모멘텀", buzz: "버즈", insider: "내부자거래",
        };
        const moduleLines = Object.entries(ms)
          .map(([k, v]) => `${moduleNames[k] ?? k}: ${v.score?.toFixed(1)}점`)
          .join(", ");
        parts.push(`모듈별 점수: ${moduleLines}`);
      }

      const ev = a.evidence as Record<string, Record<string, unknown>> | null;
      if (ev?.revenue) {
        const r = ev.revenue;
        const lines: string[] = [];
        if (r.sales_qoq_pct != null) lines.push(`매출QoQ: ${Number(r.sales_qoq_pct).toFixed(1)}%`);
        if (r.eps_qoq_pct != null) lines.push(`EPSQoQ: ${Number(r.eps_qoq_pct).toFixed(1)}%`);
        if (r.gross_margin_pct != null) lines.push(`매출총이익률: ${Number(r.gross_margin_pct).toFixed(1)}%`);
        if (r.transition_bonus) lines.push(`매출전환보너스: +${r.transition_bonus}점`);
        if (lines.length) parts.push(`실적 데이터: ${lines.join(", ")}`);
      }
      if (ev?.analyst) {
        const an = ev.analyst;
        if (an.target_price != null) parts.push(`애널리스트 목표가: $${Number(an.target_price).toFixed(0)}, 현재가: $${Number(an.current_price ?? 0).toFixed(0)}, 상승여력: ${Number(an.upside_pct ?? 0).toFixed(1)}%`);
      }
    }

    if (sec?.length) {
      parts.push(`\n=== ${ticker} SEC 공시 AI 분석 ===`);
      sec.forEach((f) => {
        parts.push(`[${f.form_type} ${f.filed_date}]`);
        if (f.ai_summary) {
          const s = f.ai_summary as Record<string, string>;
          if (s.performance_summary) parts.push(`실적: ${s.performance_summary}`);
          if (s.risk_summary) parts.push(`리스크: ${s.risk_summary}`);
          if (s.guidance_summary) parts.push(`가이던스: ${s.guidance_summary}`);
        }
        if (f.risk_flags?.length) parts.push(`리스크 플래그: ${(f.risk_flags as string[]).join(", ")}`);
      });
    }
  }

  return parts.join("\n") || "관련 데이터 없음";
}

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const rawMessages = (body as { messages?: unknown })?.messages;
  if (!Array.isArray(rawMessages) || rawMessages.length === 0) {
    return NextResponse.json({ error: "messages required" }, { status: 400 });
  }

  const messages = rawMessages
    .filter(
      (m): m is { role: string; content: string } =>
        typeof m === "object" && m !== null &&
        ["user", "assistant"].includes((m as { role: string }).role) &&
        typeof (m as { content: string }).content === "string" &&
        (m as { content: string }).content.length > 0 &&
        (m as { content: string }).content.length <= MAX_MSG_LEN
    )
    .slice(-MAX_MESSAGES);

  if (messages.length === 0) {
    return NextResponse.json({ error: "no valid messages" }, { status: 400 });
  }

  const groqKey = process.env.GROQ_API_KEY;
  if (!groqKey) return NextResponse.json({ error: "GROQ_API_KEY not configured" }, { status: 500 });

  const lastUserMsg = [...messages].reverse().find((m) => m.role === "user")?.content ?? "";
  const dbContext = await buildContext(lastUserMsg).catch(() => "컨텍스트 로드 실패");

  const systemPrompt = `You are a stock supply-demand analysis assistant for Korean retail investors.
CRITICAL: You MUST respond ONLY in Korean (한국어). Never use English, Vietnamese, or any other language. Every single word must be Korean.

[DB 컨텍스트]
${dbContext}

규칙:
- DB에 없는 데이터는 "해당 데이터가 없습니다"라고 명시
- 투자 권유·매수/매도 추천 금지
- 수급 데이터 해석 및 사실 기반 분석만 제공
- 간결하고 명확하게 답변 (3~5문장 이내 권장)
- 반드시 한국어로만 답변. 영어·베트남어·기타 언어 절대 혼용 금지`;

  const groqRes = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${groqKey}`,
    },
    body: JSON.stringify({
      model: "llama-3.3-70b-versatile",
      max_tokens: 600,
      stream: true,
      messages: [
        { role: "system", content: systemPrompt },
        ...messages.map((m) => ({ role: m.role, content: m.content })),
      ],
    }),
  });

  if (!groqRes.ok) {
    const err = await groqRes.text();
    return NextResponse.json({ error: `Groq error: ${err}` }, { status: 500 });
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const reader = groqRes.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") continue;
          try {
            const json = JSON.parse(data);
            const text = json.choices?.[0]?.delta?.content ?? "";
            if (text) controller.enqueue(encoder.encode(text));
          } catch {}
        }
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
