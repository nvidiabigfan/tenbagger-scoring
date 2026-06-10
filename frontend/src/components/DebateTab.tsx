"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Round {
  round_no: number;
  bull_text: string;
  bear_text: string;
}

interface Verdict {
  bull_score: number;
  bear_score: number;
  recommendation: string;
  verdict_text: string;
}

interface DebateData {
  available: boolean;
  bull_text?: string;
  bear_text?: string;
  score_at_gen?: number;
  generated_at?: string;
  rounds?: Round[];
  verdict?: Verdict | null;
}

type Phase = "idle" | "round1" | "round2" | "judging" | "done";

function RecommendBadge({ rec }: { rec: string }) {
  const map: Record<string, { cls: string; icon: string }> = {
    "주목할만함": { cls: "bg-green-100 text-green-700", icon: "▲" },
    "중립":       { cls: "bg-yellow-100 text-yellow-600", icon: "—" },
    "유의필요":   { cls: "bg-red-100 text-red-500", icon: "▼" },
  };
  const style = map[rec] ?? { cls: "bg-gray-100 text-gray-500", icon: "?" };
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-semibold ${style.cls}`}>
      {style.icon} {rec}
    </span>
  );
}

function ScoreBar({ label, score, barCls, textCls }: { label: string; score: number; barCls: string; textCls: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-gray-500">{label}</span>
        <span className={`font-bold tabular-nums ${textCls}`}>{score}</span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barCls}`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

function RoundCards({ round, live }: { round: Round; live: boolean }) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
        Round {round.round_no} {round.round_no === 1 ? "— 첫 주장" : "— 재반박"}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="text-base">🟢</span>
            <span className="text-sm font-bold text-green-700">
              강세론 <span className="text-xs font-normal text-green-500">(Groq)</span>
            </span>
          </div>
          <p className="text-xs text-green-900 leading-relaxed whitespace-pre-wrap">
            {round.bull_text}
            {live && !round.bull_text && <span className="text-green-400">…</span>}
          </p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="text-base">🔴</span>
            <span className="text-sm font-bold text-red-700">
              약세론 <span className="text-xs font-normal text-red-400">(Gemini)</span>
            </span>
          </div>
          <p className="text-xs text-red-900 leading-relaxed whitespace-pre-wrap">
            {round.bear_text}
            {live && !round.bear_text && <span className="text-red-300">…</span>}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function DebateTab({ ticker }: { ticker: string; inWatchlist?: boolean; onAddWatchlist?: () => void }) {
  const [data, setData] = useState<DebateData | null>(null);
  const [loading, setLoading] = useState(true);

  const [phase, setPhase] = useState<Phase>("idle");
  const [rounds, setRounds] = useState<Round[]>([]);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const generating = phase !== "idle" && phase !== "done";

  // 캐시 로드 (탭 재오픈 = 호출 0)
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/debate/${ticker}`)
      .then((r) => r.json())
      .then((d: DebateData) => {
        if (cancelled) return;
        setData(d);
        if (d.available && (d.rounds?.length || d.verdict)) {
          setRounds(d.rounds ?? []);
          setVerdict(d.verdict ?? null);
          setPhase("done");
        }
      })
      .catch(() => !cancelled && setData({ available: false }))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [ticker]);

  const appendToken = useCallback((round: number, side: "bull" | "bear", d: string) => {
    setRounds((prev) => {
      const next = prev.map((r) => ({ ...r }));
      let r = next.find((x) => x.round_no === round);
      if (!r) {
        r = { round_no: round, bull_text: "", bear_text: "" };
        next.push(r);
        next.sort((a, b) => a.round_no - b.round_no);
      }
      if (side === "bull") r.bull_text += d;
      else r.bear_text += d;
      return next;
    });
  }, []);

  const start = useCallback(async () => {
    setGenError(null);
    setRounds([]);
    setVerdict(null);
    setPhase("round1");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let produced = false;

    try {
      const res = await fetch(`/api/debate/${ticker}/generate`, { method: "POST", signal: ctrl.signal });
      if (!res.ok || !res.body) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error ?? `생성 실패 (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          const s = line.trim();
          if (!s) continue;
          let ev: Record<string, unknown>;
          try { ev = JSON.parse(s); } catch { continue; }
          switch (ev.t) {
            case "tok":
              produced = true;
              appendToken(ev.round as number, ev.side as "bull" | "bear", ev.d as string);
              break;
            case "rdone":
              if (ev.round === 1) setPhase("round2");
              break;
            case "judging":
              setPhase("judging");
              break;
            case "verdict":
              setVerdict({
                bull_score: ev.bull_score as number,
                bear_score: ev.bear_score as number,
                recommendation: ev.recommendation as string,
                verdict_text: ev.text as string,
              });
              break;
            case "done":
              setPhase("done");
              break;
            case "err":
              throw new Error((ev.m as string) ?? "생성 오류");
          }
        }
      }
      setPhase("done");
      // 생성 완료 후 메타(생성일/점수) 갱신
      fetch(`/api/debate/${ticker}`).then((r) => r.json()).then((d: DebateData) => setData(d)).catch(() => {});
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setGenError(String((e as Error).message ?? e));
      setPhase(produced ? "done" : "idle");
    }
  }, [ticker, appendToken]);

  useEffect(() => () => abortRef.current?.abort(), []);

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <div className="w-8 h-8 border-4 border-blue-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const hasContent = rounds.length > 0 || !!verdict;
  const phaseLabel: Record<Phase, string> = {
    idle: "", round1: "Round 1 토론 중…", round2: "Round 2 재반박 중…",
    judging: "심판 판정 중 (OpenAI)…", done: "",
  };

  return (
    <div className="space-y-4">
      {/* 컨트롤 바 */}
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-gray-500 min-w-0">
          {generating ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              {phaseLabel[phase]}
            </span>
          ) : hasContent && data?.generated_at ? (
            <span className="truncate">
              생성 {new Date(data.generated_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              {data.score_at_gen !== undefined && ` · 점수 ${Number(data.score_at_gen).toFixed(1)}`}
            </span>
          ) : null}
        </div>
        <button
          onClick={start}
          disabled={generating}
          className="shrink-0 text-xs px-3 py-1.5 rounded-lg border border-blue-300 text-blue-600 bg-blue-50 hover:bg-blue-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-semibold"
        >
          {generating ? "토론 진행 중…" : hasContent ? "↻ 다시 토론하기" : "▶ 토론 시작하기"}
        </button>
      </div>

      {genError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">{genError}</div>
      )}

      {!hasContent && !generating ? (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 text-center">
          <p className="text-gray-500 text-sm mb-1">강세 vs 약세 멀티에이전트 토론</p>
          <p className="text-gray-400 text-xs leading-relaxed">
            강세론(Groq) vs 약세론(Gemini)이 2라운드 토론한 뒤 중립 심판(OpenAI)이 판정합니다.
            <br />위 “토론 시작하기”를 누르면 실시간으로 생성됩니다.
          </p>
        </div>
      ) : (
        <>
          {rounds.map((r) => (
            <RoundCards key={r.round_no} round={r} live={generating} />
          ))}

          {verdict && (
            <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-base">⚖️</span>
                  <span className="text-sm font-bold text-gray-700">
                    심판 판정 <span className="text-xs font-normal text-gray-400">(OpenAI)</span>
                  </span>
                </div>
                <RecommendBadge rec={verdict.recommendation} />
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <ScoreBar label="강세 설득력" score={verdict.bull_score} barCls="bg-green-400" textCls="text-green-600" />
                <ScoreBar label="약세 설득력" score={verdict.bear_score} barCls="bg-red-400" textCls="text-red-500" />
              </div>
              <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">{verdict.verdict_text}</p>
            </div>
          )}
        </>
      )}

      <p className="text-center text-[10px] text-gray-300">본 서비스는 투자 자문이 아니며 참고용입니다.</p>
    </div>
  );
}
