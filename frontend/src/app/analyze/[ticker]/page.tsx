"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

interface ModuleResult {
  score: number;
  signal: string;
  confidence: number;
  evidence: Record<string, unknown>;
}

interface AnalyzeResult {
  ticker: string;
  total_score: number;
  signal: string;
  confidence: number;
  report_md: string;
  analyzed_at: string;
  from_cache: boolean;
  analysis_id: string;
  modules: Record<string, ModuleResult>;
}

const SIGNAL: Record<string, { label: string; cls: string }> = {
  strong_buy: { label: "강한 주목", cls: "bg-green-100 text-green-800" },
  buy:        { label: "긍정 시그널", cls: "bg-blue-100 text-blue-700" },
  hold:       { label: "중립", cls: "bg-yellow-100 text-yellow-700" },
  sell:       { label: "부정 시그널", cls: "bg-red-100 text-red-600" },
};

const MODULE_LABEL: Record<string, string> = {
  revenue:  "매출 가속도",
  etf:      "기관 수급 변화",
  analyst:  "애널리스트 컨센서스",
  size:     "시총 비대칭",
  trends:   "Google Trends 지속성",
  buzz:     "Wikipedia 관심 증가",
  youtube:  "YouTube 주목도",
};

function scoreColor(s: number) {
  if (s >= 80) return "text-green-600";
  if (s >= 60) return "text-blue-600";
  if (s >= 40) return "text-yellow-500";
  return "text-red-500";
}

const KEY_LABEL: Record<string, string> = {
  net_ratio_1m:        "애널 1개월",
  net_ratio_3m:        "애널 3개월",
  net_ratio_6m:        "애널 6개월",
  net_ratio_1y:        "애널 1년",
  composite_net:       "애널 종합",
  upside_pct:          "목표가 괴리",
  inst_trans_pct:      "기관 순매수",
  rel_volume:          "상대 거래량",
  rate_3m:             "Trends 3개월",
  rate_6m:             "Trends 6개월",
  rate_1y:             "Trends 1년",
  composite_rate:      "Trends 종합",
  coverage_count_now:  "커버리지 수",
  coverage_growth_3m:  "커버리지 증가(3m)",
};

// evidence 값 포맷
function fmtEvidence(key: string, val: unknown): string | null {
  if (val === null || val === undefined) return null;
  const k = key.toLowerCase();
  if (typeof val === "number") {
    // 소수 비율 → ×100해서 %
    if (k.includes("rate") || k.includes("ratio") || k === "composite_net") {
      const sign = val >= 0 ? "+" : "";
      return `${sign}${(val * 100).toFixed(1)}%`;
    }
    // 이미 % 단위
    if (k.includes("pct") || k === "coverage_growth_3m") {
      const sign = val >= 0 ? "+" : "";
      return `${sign}${val.toFixed(1)}%`;
    }
    // 상대 배수
    if (k === "rel_volume") return `${val.toFixed(2)}×`;
    if (k.includes("count") || k.includes("weeks") || k.includes("num")) {
      return String(Math.round(val));
    }
    return val.toFixed(1);
  }
  if (typeof val === "boolean") return val ? "예" : "아니오";
  if (typeof val === "string") return val;
  return String(val);
}

// evidence에서 표시할 항목 선별 (error, keyword 등 제외)
const SKIP_KEYS = new Set(["error", "keyword", "schema_version"]);

function EvidencePanel({ evidence }: { evidence: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);

  const entries = Object.entries(evidence)
    .filter(([k, v]) => !SKIP_KEYS.has(k) && v !== null && v !== undefined)
    .map(([k, v]) => [k, fmtEvidence(k, v)] as [string, string | null])
    .filter(([, v]) => v !== null) as [string, string][];

  if (entries.length === 0) return null;

  const isHighlight = (k: string) =>
    k.includes("rate") || k.includes("ratio") || k.includes("pct") ||
    k === "composite_net" || k === "rel_volume" || k === "coverage_growth_3m";

  const highlights = entries.filter(([k]) => isHighlight(k));
  const rest = entries.filter(([k]) => !isHighlight(k));

  const keyLabel = (k: string) =>
    KEY_LABEL[k] ?? k.replace(/_/g, " ").replace(/\b(\w)/g, (c) => c.toUpperCase());

  return (
    <div className="mt-3 border-t border-gray-100 pt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1 transition-colors"
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>근거 데이터</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {/* 변화율 하이라이트 */}
          {highlights.length > 0 && (
            <div className="grid grid-cols-2 gap-1">
              {highlights.map(([k, v]) => (
                <div key={k} className="bg-gray-50 rounded px-2 py-1">
                  <div className="text-[10px] text-gray-400">{keyLabel(k)}</div>
                  <div className={`text-xs font-semibold tabular-nums ${
                    v.startsWith("+") ? "text-green-600" : v.startsWith("-") ? "text-red-500" : "text-gray-700"
                  }`}>
                    {v}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 나머지 evidence */}
          {rest.length > 0 && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px]">
              {rest.map(([k, v]) => (
                <>
                  <dt key={`k-${k}`} className="text-gray-400 truncate">{keyLabel(k)}</dt>
                  <dd key={`v-${k}`} className="text-gray-600 tabular-nums">{v}</dd>
                </>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}

export default function AnalyzePage() {
  const { ticker } = useParams<{ ticker: string }>();
  const router = useRouter();
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [inWatchlist, setInWatchlist] = useState(false);
  const [wlLoading, setWlLoading] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      const u = data.session?.user ?? null;
      setUser(u);
      if (u && ticker) {
        const { data: row } = await supabase
          .from("watchlist")
          .select("ticker")
          .eq("user_id", u.id)
          .eq("ticker", ticker.toUpperCase())
          .maybeSingle();
        setInWatchlist(!!row);
      }
    });
  }, [ticker]);

  const toggleWatchlist = async () => {
    if (!user) { router.push("/login"); return; }
    setWlLoading(true);
    if (inWatchlist) {
      await supabase.from("watchlist").delete().eq("ticker", ticker!.toUpperCase()).eq("user_id", user.id);
      setInWatchlist(false);
    } else {
      await supabase.from("watchlist").upsert({ user_id: user.id, ticker: ticker!.toUpperCase() }, { onConflict: "user_id,ticker", ignoreDuplicates: true });
      setInWatchlist(true);
    }
    setWlLoading(false);
  };

  useEffect(() => {
    fetch(`/api/analyze/${ticker}`, { method: "POST" })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => Promise.reject(e.detail ?? "분석 실패"));
        return r.json() as Promise<AnalyzeResult>;
      })
      .then(setResult)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="flex flex-col items-center pt-24 gap-4 text-center">
        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-gray-500 text-sm">
          <span className="font-semibold">{ticker}</span> 분석 중...
        </p>
        <p className="text-gray-400 text-xs">ETF·애널리스트·StockTwits·Trends 데이터 수집 중 (최대 30초)</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center pt-20">
        <p className="text-red-500 mb-4">{error}</p>
        <button onClick={() => router.push("/")} className="text-blue-600 text-sm underline">
          ← 홈으로
        </button>
      </div>
    );
  }

  if (!result) return null;

  const sig = SIGNAL[result.signal] ?? { label: result.signal, cls: "bg-gray-100 text-gray-700" };

  return (
    <div className="max-w-2xl mx-auto">
      {/* Back */}
      <button
        onClick={() => router.push("/")}
        className="text-sm text-gray-400 hover:text-gray-700 mb-6 flex items-center gap-1"
      >
        ← 다른 종목 검색
      </button>

      {/* Score Card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 mb-6 text-center">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-3xl font-bold text-gray-900">{result.ticker}</h1>
          <button
            onClick={toggleWatchlist}
            disabled={wlLoading}
            className={`text-sm px-3 py-1.5 rounded-lg border transition-colors ${
              inWatchlist
                ? "border-blue-300 text-blue-600 bg-blue-50 hover:bg-red-50 hover:text-red-500 hover:border-red-200"
                : "border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
            }`}
            title={inWatchlist ? "워치리스트에서 제거" : "워치리스트에 추가"}
          >
            {inWatchlist ? "★ 추가됨" : "☆ 워치리스트"}
          </button>
        </div>
        <div className={`text-8xl font-black my-5 tabular-nums ${scoreColor(result.total_score)}`}>
          {result.total_score}
        </div>
        <span className={`inline-block px-4 py-1.5 rounded-full text-sm font-semibold ${sig.cls}`}>
          {sig.label}
        </span>
        <div className="mt-3 flex justify-center gap-6 text-sm text-gray-400">
          <span>신뢰도 {(result.confidence * 100).toFixed(0)}%</span>
          <span>{result.from_cache ? "캐시" : "신규 분석"}</span>
          <span>{new Date(result.analyzed_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
        </div>
      </div>

      {/* Module Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        {Object.entries(result.modules).map(([name, m]) => {
          const ms = SIGNAL[m.signal] ?? { label: m.signal, cls: "bg-gray-100 text-gray-700" };
          return (
            <div key={name} className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
              <div className="flex justify-between items-center mb-3">
                <div>
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{name}</span>
                  {MODULE_LABEL[name] && (
                    <div className="text-[10px] text-gray-400 mt-0.5">{MODULE_LABEL[name]}</div>
                  )}
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ms.cls}`}>{ms.label}</span>
              </div>
              <div className={`text-4xl font-bold ${scoreColor(m.score)}`}>{m.score}</div>

              {/* 점수 바 */}
              <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    m.score >= 80 ? "bg-green-400" : m.score >= 60 ? "bg-blue-400" : m.score >= 40 ? "bg-yellow-400" : "bg-red-400"
                  }`}
                  style={{ width: `${m.score}%` }}
                />
              </div>

              <div className="text-xs text-gray-400 mt-1">신뢰도 {(m.confidence * 100).toFixed(0)}%</div>

              {/* Evidence 패널 */}
              {m.evidence && Object.keys(m.evidence).length > 0 && (
                <EvidencePanel evidence={m.evidence} />
              )}
            </div>
          );
        })}
      </div>

      {/* Report */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4 uppercase tracking-wide">분석 리포트</h2>
        <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">
          {result.report_md}
        </pre>
      </div>

      <p className="text-center text-xs text-gray-300 mt-8">
        본 서비스는 투자 자문이 아니며 참고용입니다.
      </p>
    </div>
  );
}
