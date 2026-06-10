import { NextRequest, NextResponse } from "next/server";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

// 토론은 LLM 5회 호출(R1 2 + R2 2 + 심판 1) → 길게는 40초. 기본 타임아웃 상향.
export const maxDuration = 60;
export const dynamic = "force-dynamic";

// 라이브 멀티에이전트 토론 생성 (버튼 트리거 + 토큰 스트리밍)
// 강세=Groq, 약세=Gemini 2라운드 → Groq 심판. GEMINI_API_KEY 없으면 Groq fallback.
// 오케스트레이션 단일 소스: 기존 Python debate.py 를 이식. (배치 생성 제거됨)

const GROQ_URL = "https://api.groq.com/openai/v1/chat/completions";
const GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";
const OPENAI_URL = "https://api.openai.com/v1/chat/completions";
const GROQ_MODEL = "llama-3.3-70b-versatile";
const GEMINI_MODEL = "gemini-2.5-flash";
const OPENAI_JUDGE_MODEL = "gpt-4o-mini"; // 중립 제3자 심판
const MAX_TOKENS_DEBATE = 600;
const MAX_TOKENS_JUDGE = 500;

const SYS_BULL = `한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 강세론자 애널리스트다. 이 종목의 성장·상승 논거를 evidence 수치 근거로 제시한다.
규칙:
- 직접 매수 권유 금지. "주목할 만함" 식 완곡 표현.
- 반드시 제공된 evidence 수치를 인용. 없는 데이터 추정 금지.
- 4~6문장으로 작성.`;

const SYS_BEAR = `한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 약세론자 애널리스트다. 이 종목의 리스크·하락·과열 논거를 evidence 수치 근거로 제시한다.
규칙:
- 직접 매도 권유 금지. "유의 필요" 식 완곡 표현.
- 반드시 제공된 evidence 수치를 인용. 없는 데이터 추정 금지.
- 4~6문장으로 작성.`;

const SYS_JUDGE = `한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 시니어 심판 애널리스트다. 강세론자와 약세론자의 2라운드 토론 전체를 읽고 종합 판정을 내린다.
반드시 아래 JSON 형식으로만 출력하라 (다른 텍스트 금지):
{"bull_score": <0-100>, "bear_score": <0-100>, "recommendation": "<주목할만함|중립|유의필요>", "verdict": "<3~5문장 종합 분석>"}
규칙:
- bull_score + bear_score 는 각각 독립 설득력 평가 (합이 100일 필요 없음).
- recommendation은 반드시 셋 중 하나: 주목할만함, 중립, 유의필요`;

type Msg = { role: string; content: string };

function clean(text: string): string {
  return text
    .replace(/[一-鿿぀-ヿ＀-￯㐀-䶿]+/g, "")
    .replace(/[Ạ-ỹ]/g, "")
    .replace(/(?<![A-Z0-9$%])([a-z]{2,})(?![a-z])/g, "");
}

function getServiceClient(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL/SUPABASE_SERVICE_KEY env not configured");
  return createClient(url, key);
}

const MODULE_LABELS: Record<string, string> = {
  revenue: "매출성장", etf: "ETF흐름", analyst: "애널리스트", size: "시총",
  momentum: "모멘텀", buzz: "버즈", insider: "내부자", congress: "의회",
};

interface AnalysisCtx {
  totalScore: number;
  signal: string;
  confidence: number;
  scores: Record<string, number>;
  evidence: Record<string, Record<string, unknown>>;
}

async function loadAnalysis(sb: SupabaseClient, ticker: string): Promise<AnalysisCtx | null> {
  const { data: ar } = await sb
    .from("analysis_results")
    .select("id, total_score, signal, confidence")
    .eq("ticker", ticker)
    .order("analyzed_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!ar) return null;

  const { data: modules } = await sb
    .from("module_scores")
    .select("module_name, score, evidence")
    .eq("analysis_id", ar.id);

  const scores: Record<string, number> = {};
  const evidence: Record<string, Record<string, unknown>> = {};
  for (const m of modules ?? []) {
    scores[m.module_name] = Number(m.score);
    evidence[m.module_name] = (m.evidence as Record<string, unknown>) ?? {};
  }
  return {
    totalScore: Number(ar.total_score),
    signal: ar.signal,
    confidence: Number(ar.confidence),
    scores,
    evidence,
  };
}

function buildUserPrompt(ticker: string, ctx: AnalysisCtx): string {
  const scoreOf = (name: string) =>
    ctx.scores[name] !== undefined ? `${Math.round(ctx.scores[name])}점` : "N/A";

  const rev = ctx.evidence.revenue ?? {};
  const an = ctx.evidence.analyst ?? {};
  const lines: string[] = [];
  const num = (v: unknown) => (v == null ? null : Number(v));
  if (num(rev.sales_qoq_pct) != null) lines.push(`매출QoQ ${num(rev.sales_qoq_pct)!.toFixed(1)}%`);
  if (num(rev.eps_qoq_pct) != null) lines.push(`EPSQoQ ${num(rev.eps_qoq_pct)!.toFixed(1)}%`);
  if (num(rev.gross_margin_pct) != null) lines.push(`매출총이익률 ${num(rev.gross_margin_pct)!.toFixed(1)}%`);
  if (num(an.upside_pct) != null) lines.push(`상승여력 ${num(an.upside_pct)!.toFixed(1)}%`);
  if (num(an.target_price) != null) lines.push(`목표가 $${num(an.target_price)!.toFixed(0)}`);
  if (num(an.current_price) != null) lines.push(`현재가 $${num(an.current_price)!.toFixed(0)}`);

  const modLine = Object.keys(MODULE_LABELS)
    .map((k) => `${MODULE_LABELS[k]} ${scoreOf(k)}`)
    .join(", ");

  return (
    `[종목] ${ticker} / 총점 ${ctx.totalScore.toFixed(1)}(${ctx.signal}) / 신뢰도 ${Math.round(ctx.confidence * 100)}%\n` +
    `[모듈별] ${modLine}\n` +
    `[핵심 evidence] ${lines.join(", ") || "데이터 없음"}`
  );
}

// 스트리밍 LLM 호출: delta 마다 onToken(cleaned) 호출, 최종 누적 텍스트 반환
async function streamLLM(
  provider: "groq" | "gemini",
  messages: Msg[],
  onToken: (chunk: string) => void
): Promise<string> {
  const groqKey = process.env.GROQ_API_KEY ?? "";
  const geminiKey = process.env.GEMINI_API_KEY ?? "";

  let url = GROQ_URL;
  let model = GROQ_MODEL;
  let key = groqKey;
  if (provider === "gemini" && geminiKey) {
    url = GEMINI_URL;
    model = GEMINI_MODEL;
    key = geminiKey;
  }
  // gemini 키 없으면 groq fallback (위 기본값 유지)

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: JSON.stringify({ model, max_tokens: MAX_TOKENS_DEBATE, stream: true, messages }),
  });
  if (!res.ok) throw new Error(`${provider} ${res.status}: ${await res.text()}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let full = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const ls = buf.split("\n");
    buf = ls.pop() ?? "";
    for (const line of ls) {
      if (!line.startsWith("data: ")) continue;
      const d = line.slice(6).trim();
      if (d === "[DONE]") continue;
      try {
        const j = JSON.parse(d);
        const raw = j.choices?.[0]?.delta?.content ?? "";
        const t = clean(raw);
        if (t) {
          full += t;
          onToken(t);
        }
      } catch {}
    }
  }
  return full;
}

// 심판: 중립 제3자 OpenAI(gpt-4o-mini, JSON 모드). OPENAI_API_KEY 없으면 Groq fallback.
async function callJudge(messages: Msg[]): Promise<{ raw: string; agent: string }> {
  const openaiKey = process.env.OPENAI_API_KEY ?? "";
  if (openaiKey) {
    const res = await fetch(OPENAI_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${openaiKey}` },
      body: JSON.stringify({
        model: OPENAI_JUDGE_MODEL,
        max_tokens: MAX_TOKENS_JUDGE,
        response_format: { type: "json_object" },
        messages,
      }),
    });
    if (!res.ok) throw new Error(`judge(openai) ${res.status}: ${await res.text()}`);
    const j = await res.json();
    return { raw: j.choices?.[0]?.message?.content ?? "", agent: OPENAI_JUDGE_MODEL };
  }

  // fallback: Groq
  const res = await fetch(GROQ_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.GROQ_API_KEY ?? ""}` },
    body: JSON.stringify({ model: GROQ_MODEL, max_tokens: MAX_TOKENS_JUDGE, messages }),
  });
  if (!res.ok) throw new Error(`judge(groq) ${res.status}: ${await res.text()}`);
  const j = await res.json();
  return { raw: j.choices?.[0]?.message?.content ?? "", agent: GROQ_MODEL };
}

interface Verdict {
  bull_score: number;
  bear_score: number;
  recommendation: string;
  text: string;
}

function parseVerdict(raw: string): Verdict {
  const clamp = (n: number) => Math.max(0, Math.min(100, Math.round(n)));
  try {
    const m = raw.match(/\{[\s\S]*\}/);
    if (m) {
      const d = JSON.parse(m[0]);
      return {
        bull_score: clamp(Number(d.bull_score ?? 50)),
        bear_score: clamp(Number(d.bear_score ?? 50)),
        recommendation: d.recommendation ?? "중립",
        text: clean(String(d.verdict ?? "")),
      };
    }
  } catch {}
  return { bull_score: 50, bear_score: 50, recommendation: "중립", text: clean(raw.slice(0, 300)) };
}

export async function POST(
  _req: NextRequest,
  { params }: { params: { ticker: string } }
) {
  const ticker = params.ticker.toUpperCase().replace(/[^A-Z.]/g, "").slice(0, 6);
  if (!ticker) return NextResponse.json({ error: "invalid ticker" }, { status: 400 });
  if (!process.env.GROQ_API_KEY) {
    return NextResponse.json({ error: "GROQ_API_KEY not configured" }, { status: 500 });
  }

  const sb = getServiceClient();
  const ctx = await loadAnalysis(sb, ticker);
  if (!ctx) {
    return NextResponse.json(
      { error: "분석 결과가 없습니다. 먼저 종목 분석이 필요합니다." },
      { status: 409 }
    );
  }

  const userPrompt = buildUserPrompt(ticker, ctx);
  const bearProvider: "groq" | "gemini" = process.env.GEMINI_API_KEY ? "gemini" : "groq";
  const bearAgent = bearProvider === "gemini" ? "gemini" : "groq";

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (obj: unknown) => controller.enqueue(encoder.encode(JSON.stringify(obj) + "\n"));

      // 세션 생성
      const { data: sessionRow, error: sErr } = await sb
        .from("debate_sessions")
        .insert({
          ticker,
          total_rounds: 2,
          status: "running",
          score_at_gen: ctx.totalScore,
          signal_at_gen: ctx.signal,
        })
        .select("id")
        .single();
      if (sErr || !sessionRow) {
        send({ t: "err", m: "세션 생성 실패" });
        controller.close();
        return;
      }
      const sessionId = sessionRow.id as string;

      try {
        // Round 1: 강세(Groq) + 약세(Gemini) 동시
        const [r1Bull, r1Bear] = await Promise.all([
          streamLLM("groq", [
            { role: "system", content: SYS_BULL },
            { role: "user", content: userPrompt },
          ], (d) => send({ t: "tok", round: 1, side: "bull", d })),
          streamLLM(bearProvider, [
            { role: "system", content: SYS_BEAR },
            { role: "user", content: userPrompt },
          ], (d) => send({ t: "tok", round: 1, side: "bear", d })),
        ]);
        await sb.from("debate_rounds").insert({
          session_id: sessionId, round_no: 1,
          bull_agent: "groq", bear_agent: bearAgent,
          bull_text: r1Bull, bear_text: r1Bear,
        });
        send({ t: "rdone", round: 1 });

        // Round 2: 상대 R1 읽고 재반박 동시
        const [r2Bull, r2Bear] = await Promise.all([
          streamLLM("groq", [
            { role: "system", content: SYS_BULL },
            { role: "user", content: userPrompt },
            { role: "assistant", content: r1Bull },
            { role: "user", content: `상대방 약세 주장:\n${r1Bear}\n\n위 약세 주장의 허점을 반박하고 강세 논거를 보완하라.` },
          ], (d) => send({ t: "tok", round: 2, side: "bull", d })),
          streamLLM(bearProvider, [
            { role: "system", content: SYS_BEAR },
            { role: "user", content: userPrompt },
            { role: "assistant", content: r1Bear },
            { role: "user", content: `상대방 강세 주장:\n${r1Bull}\n\n위 강세 주장의 허점을 반박하고 약세 논거를 보완하라.` },
          ], (d) => send({ t: "tok", round: 2, side: "bear", d })),
        ]);
        await sb.from("debate_rounds").insert({
          session_id: sessionId, round_no: 2,
          bull_agent: "groq", bear_agent: bearAgent,
          bull_text: r2Bull, bear_text: r2Bear,
        });
        send({ t: "rdone", round: 2 });

        // Judge
        send({ t: "judging" });
        const judgePrompt =
          `[강세 R1]\n${r1Bull}\n\n[약세 R1]\n${r1Bear}\n\n[강세 R2]\n${r2Bull}\n\n[약세 R2]\n${r2Bear}`;
        const { raw: verdictRaw, agent: judgeAgent } = await callJudge([
          { role: "system", content: SYS_JUDGE },
          { role: "user", content: judgePrompt },
        ]);
        const verdict = parseVerdict(verdictRaw);
        await sb.from("debate_verdicts").insert({
          session_id: sessionId, judge_agent: judgeAgent,
          verdict_text: verdict.text,
          bull_score: verdict.bull_score, bear_score: verdict.bear_score,
          recommendation: verdict.recommendation,
        });
        await sb.from("debate_sessions").update({
          status: "completed", completed_at: new Date().toISOString(),
        }).eq("id", sessionId);

        // GET 라우트의 available 게이트 = debates 테이블. 최종 R2 텍스트 upsert.
        await sb.from("debates").upsert({
          ticker, bull_text: r2Bull, bear_text: r2Bear,
          score_at_gen: ctx.totalScore, signal_at_gen: ctx.signal,
          model: `${GROQ_MODEL} vs ${bearAgent === "gemini" ? GEMINI_MODEL : GROQ_MODEL}`,
          generated_at: new Date().toISOString(),
        }, { onConflict: "ticker" });

        send({
          t: "verdict",
          bull_score: verdict.bull_score, bear_score: verdict.bear_score,
          recommendation: verdict.recommendation, text: verdict.text,
        });
        send({ t: "done" });
      } catch (e) {
        await sb.from("debate_sessions").update({ status: "failed" }).eq("id", sessionId);
        send({ t: "err", m: String(e) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: { "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-store" },
  });
}
