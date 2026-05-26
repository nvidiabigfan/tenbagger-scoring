"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

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

function scoreColor(s: number) {
  if (s >= 80) return "text-green-600";
  if (s >= 60) return "text-blue-600";
  if (s >= 40) return "text-yellow-500";
  return "text-red-500";
}

export default function AnalyzePage() {
  const { ticker } = useParams<{ ticker: string }>();
  const router = useRouter();
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/analyze/${ticker}`, {
      method: "POST",
    })
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
        <p className="text-gray-400 text-xs">ETF·애널리스트 데이터 수집 중 (최대 10초)</p>
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
        <h1 className="text-3xl font-bold text-gray-900 mb-1">{result.ticker}</h1>
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
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ms.cls}`}>{ms.label}</span>
              </div>
              <div className={`text-4xl font-bold ${scoreColor(m.score)}`}>{m.score}</div>
              <div className="text-xs text-gray-400 mt-1">신뢰도 {(m.confidence * 100).toFixed(0)}%</div>
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
    </div>
  );
}
