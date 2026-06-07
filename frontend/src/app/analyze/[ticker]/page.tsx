"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";
import dynamic from "next/dynamic";

const SupplyTab = dynamic(() => import("@/components/SupplyTab"), { ssr: false });
const SecReportTab = dynamic(() => import("@/components/SecReportTab"), { ssr: false });
const ChatTab = dynamic(() => import("@/components/ChatTab"), { ssr: false });

type TabKey = "score" | "supply" | "sec" | "chat";
const TABS: { key: TabKey; label: string }[] = [
  { key: "score", label: "성장점수" },
  { key: "supply", label: "수급" },
  { key: "sec", label: "SEC 리포트" },
  { key: "chat", label: "AI Q&A" },
];

interface GrowthContext {
  available: boolean;
  currentScore?: number;
  topPct?: number;
  universeSize?: number;
  delta?: number | null;
  history?: { week_date: string; total_score: number }[];
}

function growthLabel(topPct: number, delta: number | null) {
  if (topPct <= 15 && delta !== null && delta >= 5)
    return { text: "🔥 폭발적 성장", cls: "bg-orange-50 border-orange-200 text-orange-700" };
  if (topPct <= 15)
    return { text: "★ 최상위 유지", cls: "bg-green-50 border-green-200 text-green-700" };
  if (topPct <= 40 && delta !== null && delta >= 5)
    return { text: "↑ 성장 가속", cls: "bg-blue-50 border-blue-200 text-blue-700" };
  if (topPct <= 40)
    return { text: "→ 성장 중", cls: "bg-blue-50 border-blue-100 text-blue-600" };
  if (delta !== null && delta <= -5)
    return { text: "↓ 성장 둔화", cls: "bg-red-50 border-red-200 text-red-600" };
  return { text: "— 정체", cls: "bg-gray-50 border-gray-200 text-gray-500" };
}

function Sparkline({ data }: { data: number[] }) {
  const W = 240, H = 40, PAD = 3;
  const scores = data.map((d) => d);
  const dataMin = Math.min(...scores);
  const dataMax = Math.max(...scores);
  const pad = Math.max((dataMax - dataMin) * 0.5, 0.5);
  const min = Math.max(0, dataMin - pad);
  const max = Math.min(100, dataMax + pad);
  const range = max - min || 1;
  const toY = (v: number) => PAD + (H - PAD * 2) * (1 - (v - min) / range);
  const toX = (i: number) => scores.length < 2 ? W / 2 : (i / (scores.length - 1)) * W;

  const pts = scores.map((v, i) => `${toX(i)},${toY(v)}`).join(" ");
  const last = { x: toX(scores.length - 1), y: toY(scores[scores.length - 1]) };

  const areaPath =
    `M ${toX(0)},${H} ` +
    scores.map((v, i) => `L ${toX(i)},${toY(v)}`).join(" ") +
    ` L ${toX(scores.length - 1)},${H} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ height: "auto" }} className="overflow-visible">
      <defs>
        <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#sg)" />
      {scores.length >= 2 && (
        <polyline points={pts} fill="none" stroke="#3b82f6" strokeWidth="2"
          strokeLinejoin="round" strokeLinecap="round" />
      )}
      <circle cx={last.x} cy={last.y} r="4" fill="#3b82f6" />
    </svg>
  );
}

function GrowthContextCard({ ctx }: { ctx: GrowthContext }) {
  if (!ctx.available || ctx.topPct === undefined) return null;
  const delta = ctx.delta ?? null;
  const label = growthLabel(ctx.topPct, delta);
  const scores = ctx.history?.map((h) => h.total_score) ?? [];
  const weeks = ctx.history?.map((h) => {
    const d = new Date(h.week_date);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  }) ?? [];

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 mb-3">
      {/* 레이블 + 분위수 한 줄 */}
      <div className="flex items-center justify-between mb-2">
        <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-bold border ${label.cls}`}>
          {label.text}
        </span>
        <div className="flex items-center gap-2">
          {delta !== null && (
            <span className={`text-xs font-semibold tabular-nums ${delta >= 0 ? "text-green-600" : "text-red-500"}`}>
              {delta >= 0 ? `+${delta}` : delta}점
            </span>
          )}
          <div className="text-right">
            <div className="text-[10px] text-gray-400">전체 {ctx.universeSize}종목 중</div>
            <div className="text-sm font-black text-gray-800">상위 {ctx.topPct}%</div>
          </div>
        </div>
      </div>

      {/* 추이 차트 */}
      {scores.length >= 1 && (
        <div className="w-full overflow-hidden">
          <Sparkline data={scores} />
          {weeks.length >= 2 && (
            <div className="flex justify-between text-[9px] text-gray-300 mt-0.5 w-full">
              <span>{weeks[0]} <span className="text-gray-400 font-medium">{scores[0].toFixed(1)}</span></span>
              <span><span className="text-gray-400 font-medium">{scores[scores.length - 1].toFixed(1)}</span> {weeks[weeks.length - 1]}</span>
            </div>
          )}
        </div>
      )}

      {scores.length < 2 && (
        <p className="text-[10px] text-gray-300 mt-1">
          추이 그래프는 2주 이상 데이터 누적 후 표시됩니다.
        </p>
      )}
    </div>
  );
}

interface ModuleResult {
  score: number;
  signal: string;
  confidence: number;
  evidence: Record<string, unknown>;
  weight?: number;
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
  momentum: "주가 모멘텀",
  buzz:     "Wikipedia 관심 증가",
  insider:  "내부자 거래",
  congress: "의회 순매수",
  trends:   "Google Trends 지속성",
  youtube:  "YouTube 주목도",
};

const MODULE_WEIGHT: Record<string, number> = {
  revenue:  25,
  etf:      20,
  analyst:  15,
  size:     15,
  momentum: 10,
  buzz:     10,
  insider:  3,
  congress: 2,
  trends:   15,
  youtube:  10,
};

function scoreColor(s: number) {
  if (s >= 80) return "text-green-600";
  if (s >= 60) return "text-blue-600";
  if (s >= 40) return "text-yellow-500";
  return "text-red-500";
}

const KEY_LABEL: Record<string, string> = {
  // ── Analyst ──────────────────────────────────────
  net_ratio_1m:           "애널 1개월 (Net Ratio 1M)",
  net_ratio_3m:           "애널 3개월 (Net Ratio 3M)",
  net_ratio_6m:           "애널 6개월 (Net Ratio 6M)",
  net_ratio_1y:           "애널 1년 (Net Ratio 1Y)",
  composite_net:          "애널 종합 (Composite Net)",
  upside_pct:             "목표가 괴리 (Upside %)",
  ratings_count:          "레이팅 수 (Ratings Count)",
  ratings_count_1y:       "1년 레이팅 수 (Ratings Count 1Y)",
  target_price:           "목표가 (Target Price)",
  current_price:          "현재가 (Current Price)",
  mode:                   "분석 모드 (Mode)",
  recom:                  "추천 지수 (Recom)",
  recom_fallback:         "추천 폴백 여부 (Recom Fallback)",
  coverage_count_now:     "커버리지 수 (Coverage Count)",
  coverage_growth_3m:     "커버리지 증가 3개월 (Coverage Growth 3M)",
  coverage_count_90d_ago: "90일 전 커버리지 (Coverage 90D Ago)",
  coverage_snapshot_date: "스냅샷 날짜 (Snapshot Date)",
  analyst_density_bonus:  "애널 밀도 보너스 (Analyst Density Bonus)",
  mc_billions:            "시총 십억$ (Mc Billions)",

  // ── ETF ──────────────────────────────────────────
  inst_trans_pct:         "기관 순매수 (Inst Trans %)",
  inst_trans_score:       "기관 순매수 점수 (Inst Trans Score)",
  inst_own_pct:           "기관 보유율 (Inst Own %)",
  rel_volume:             "상대 거래량 (Rel Volume)",
  rel_volume_score:       "상대 거래량 점수 (Rel Volume Score)",
  volume_score:           "거래량 점수 (Volume Score)",

  // ── Revenue ──────────────────────────────────────
  sales_qoq_pct:          "매출 전분기 대비 (Sales QoQ%)",
  sales_5y_avg_pct:       "매출 5년 평균 성장률 (Sales 5Y Avg%)",
  sales_3y_avg_pct:       "매출 3년 평균 성장률 (Sales 3Y Avg%)",
  accel_delta_pct:        "매출 가속도 변화 (Accel Delta%)",
  eps_qoq_pct:            "EPS 전분기 대비 (EPS QoQ%)",
  eps_5y_avg_pct:         "EPS 5년 평균 성장률 (EPS 5Y Avg%)",
  gross_margin_pct:       "매출총이익률 (Gross Margin%)",
  sales_score:            "매출 점수 (Sales Score)",
  accel_score:            "가속도 점수 (Accel Score)",
  eps_score:              "EPS 점수 (Eps Score)",
  transition_bonus:       "매출 음→양 전환 보너스 (Transition Bonus)",
  eps_flip_bonus:         "EPS 음→양 전환 보너스 (EPS Flip Bonus)",

  // ── Momentum ─────────────────────────────────────
  perf_1w:                "수익률 1주 (Perf 1W)",
  perf_1m:                "수익률 1개월 (Perf 1M)",
  perf_3m:                "수익률 3개월 (Perf 3M)",
  perf_composite:         "모멘텀 종합 (Perf Composite)",
  rsi:                    "RSI (14일)",
  range_52w:              "52주 범위 위치 (Range 52W)",

  // ── Buzz ─────────────────────────────────────────
  recent_30d_avg:         "최근 30일 평균 조회수 (Recent 30D Avg)",
  prev_30d_avg:           "직전 30일 평균 조회수 (Prev 30D Avg)",
  m3_30d_avg:             "3개월 전 30일 평균 조회수 (M3 30D Avg)",
  days_collected:         "수집 일수 (Days Collected)",
  news_count_30d:         "뉴스 수 30일 (News Count 30D)",
  mom_ratio:              "버즈 전월 대비 (MoM Ratio)",
  consecutive_growth_3m:  "3개월 연속 상승 여부 (Consecutive Growth 3M)",
  wiki_title:             "위키피디아 제목 (Wiki Title)",
  avg_views:              "평균 조회수 (Avg Views)",
  avg_3m:                 "3개월 평균 (Avg 3M)",
  avg_6m_ago:             "6개월 전 평균 (Avg 6M Ago)",
  avg_9m_ago:             "9개월 전 평균 (Avg 9M Ago)",
  avg_12m_ago:            "12개월 전 평균 (Avg 12M Ago)",

  // ── Size ─────────────────────────────────────────
  cap_zone:               "시총 구간 (Cap Zone)",
  market_cap_b:           "시총 십억$ (Market Cap B)",
  market_cap_raw:         "시총 원값 (Market Cap Raw)",

  // ── Insider ──────────────────────────────────────
  insider_trans_pct:      "내부자 순매수 (Insider Trans %)",
  insider_own_pct:        "내부자 보유율 (Insider Own %)",
  insider_own:            "내부자 보유 (Insider Own)",

  // ── Congress (의회 매매) ─────────────────────────
  net_buy:                "의회 순매수 (매수-매도)",
  buys:                   "매수 건수 (Buys)",
  sells:                  "매도 건수 (Sells)",
  buy_reps:               "매수 의원 수 (Buy Reps)",
  avg_excess_return_pct:  "매수의원 평균 초과수익 (Avg Excess Return %)",
  window_days:            "집계 기간 (일)",

  // ── Trends ───────────────────────────────────────
  rate_3m:                "Trends 3개월 변화율 (Rate 3M)",
  rate_6m:                "Trends 6개월 변화율 (Rate 6M)",
  rate_1y:                "Trends 1년 변화율 (Rate 1Y)",
  composite_rate:         "Trends 종합 변화율 (Composite Rate)",
  persistence_ratio:      "Trends 지속성 비율 (Persistence Ratio)",
  q4_avg:                 "최근 3개월 평균 관심도 (Q4 Avg)",
};

// evidence 값 포맷
function fmtEvidence(key: string, val: unknown): string | null {
  if (val === null || val === undefined) return null;
  const k = key.toLowerCase();
  if (typeof val === "number") {
    // 배수 비율 → (val-1)×100 % 변화 표시
    if (k === "mom_ratio" || k === "persistence_ratio") {
      const sign = (val - 1) >= 0 ? "+" : "";
      return `${sign}${((val - 1) * 100).toFixed(1)}%`;
    }
    // 보너스 점수 → +n.n 형식
    if (k.includes("bonus")) {
      return val > 0 ? `+${val.toFixed(1)}` : val.toFixed(1);
    }
    // 소수 비율 → ×100해서 %
    if (k.includes("rate") || k.includes("ratio") || k === "composite_net") {
      const sign = val >= 0 ? "+" : "";
      return `${sign}${(val * 100).toFixed(1)}%`;
    }
    // 이미 % 단위
    if (k.includes("pct") || k === "coverage_growth_3m" ||
        k === "perf_1w" || k === "perf_1m" || k === "perf_3m") {
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
    k.includes("bonus") || k === "composite_net" || k === "rel_volume" ||
    k === "coverage_growth_3m" || k === "consecutive_growth_3m" ||
    k === "perf_1w" || k === "perf_1m" || k === "perf_3m";

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
                <React.Fragment key={k}>
                  <dt className="text-gray-400 truncate">{keyLabel(k)}</dt>
                  <dd className="text-gray-600 tabular-nums">{v}</dd>
                </React.Fragment>
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
  const [growthCtx, setGrowthCtx] = useState<GrowthContext | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("score");

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
    fetch(`/api/growth-context/${ticker}`)
      .then((r) => r.json())
      .then(setGrowthCtx)
      .catch(() => {});
  }, [ticker]);

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
        <p className="text-gray-400 text-xs">매출·ETF·애널·모멘텀·버즈·내부자 데이터 수집 중 (최대 30초)</p>
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
        className="text-xs text-gray-400 hover:text-gray-700 mb-3 flex items-center gap-1"
      >
        ← 다른 종목 검색
      </button>

      {/* Score Card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-5 mb-3">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-bold text-gray-900">{result.ticker}</h1>
          <button
            onClick={toggleWatchlist}
            disabled={wlLoading}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
              inWatchlist
                ? "border-blue-300 text-blue-600 bg-blue-50 hover:bg-red-50 hover:text-red-500 hover:border-red-200"
                : "border-gray-200 text-gray-500 hover:border-blue-300 hover:text-blue-600"
            }`}
            title={inWatchlist ? "워치리스트에서 제거" : "워치리스트에 추가"}
          >
            {inWatchlist ? "★ 추가됨" : "☆ 워치리스트"}
          </button>
        </div>
        <div className={`text-5xl sm:text-6xl font-black my-3 tabular-nums text-center ${scoreColor(result.total_score)}`}>
          {result.total_score}
        </div>
        <div className="flex items-center justify-center gap-3">
          <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${sig.cls}`}>
            {sig.label}
          </span>
          <span className="text-xs text-gray-400">신뢰도 {(result.confidence * 100).toFixed(0)}%</span>
          <span className="text-xs text-gray-400">{result.from_cache ? "캐시" : "신규"}</span>
          <span className="text-xs text-gray-400">{new Date(result.analyzed_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
        </div>
      </div>

      {/* 탭 네비게이션 */}
      <div className="flex border-b border-gray-100 mb-3">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
              activeTab === t.key
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-400 hover:text-gray-600"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 탭 콘텐츠 */}
      {activeTab === "score" && (
        <>
          {/* Growth Context Card */}
          {growthCtx && <GrowthContextCard ctx={growthCtx} />}

          {/* Module Cards */}
          <div className="grid grid-cols-2 gap-2 mb-3">
            {Object.entries(result.modules).map(([name, m]) => {
              const ms = SIGNAL[m.signal] ?? { label: m.signal, cls: "bg-gray-100 text-gray-700" };
              return (
                <div key={name} className="bg-white rounded-xl border border-gray-100 shadow-sm p-3">
                  <div className="flex justify-between items-start mb-1.5">
                    <div>
                      <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">{name}</span>
                      {MODULE_LABEL[name] && (
                        <div className="text-[10px] text-gray-400">{MODULE_LABEL[name]}</div>
                      )}
                      {(m.weight ?? MODULE_WEIGHT[name]) !== undefined && (
                        <div className="text-[9px] text-gray-300 mt-0.5">배점 {m.weight ?? MODULE_WEIGHT[name]}점</div>
                      )}
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0 ml-1 ${ms.cls}`}>{ms.label}</span>
                  </div>
                  <div className={`text-3xl font-bold ${scoreColor(m.score)}`}>{m.score}</div>

                  <div className="mt-1.5 h-1 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        m.score >= 80 ? "bg-green-400" : m.score >= 60 ? "bg-blue-400" : m.score >= 40 ? "bg-yellow-400" : "bg-red-400"
                      }`}
                      style={{ width: `${m.score}%` }}
                    />
                  </div>

                  <div className="text-[10px] text-gray-400 mt-1">신뢰도 {(m.confidence * 100).toFixed(0)}%</div>

                  {m.evidence && Object.keys(m.evidence).length > 0 && (
                    <EvidencePanel evidence={m.evidence} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Report */}
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
            <h2 className="text-xs font-semibold text-gray-500 mb-3 uppercase tracking-wide">분석 리포트</h2>
            <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">
              {result.report_md}
            </pre>
          </div>
        </>
      )}

      {activeTab === "supply" && <SupplyTab ticker={result.ticker} />}
      {activeTab === "sec" && <SecReportTab ticker={result.ticker} />}
      {activeTab === "chat" && <ChatTab ticker={result.ticker} />}

      <p className="text-center text-xs text-gray-300 mt-4 mb-2">
        본 서비스는 투자 자문이 아니며 참고용입니다.
      </p>
    </div>
  );
}
