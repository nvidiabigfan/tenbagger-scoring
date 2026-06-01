"use client";

import { useEffect, useState } from "react";

const SEC_API = "/api/sec";

interface AiSummary {
  performance_summary?: string;
  risk_summary?: string;
  guidance_summary?: string;
}

interface SecFiling {
  id: string;
  ticker: string;
  form_type: string;
  filed_date: string;
  report_period: string | null;
  edgar_url: string | null;
  ai_summary: AiSummary | null;
  risk_flags: string[] | null;
  analyzed_at: string | null;
}

const RISK_LABEL: Record<string, string> = {
  revenue_decline: "매출 감소",
  margin_pressure: "마진 압박",
  guidance_cut: "가이던스 하향",
  litigation_risk: "소송 리스크",
  debt_concern: "부채 우려",
  competition_risk: "경쟁 심화",
  macro_risk: "거시 리스크",
  insider_selling: "경영진 변동",
};

const RISK_COLOR: Record<string, string> = {
  revenue_decline: "bg-red-50 border-red-200 text-red-600",
  margin_pressure: "bg-orange-50 border-orange-200 text-orange-600",
  guidance_cut: "bg-red-50 border-red-200 text-red-600",
  litigation_risk: "bg-yellow-50 border-yellow-200 text-yellow-600",
  debt_concern: "bg-orange-50 border-orange-200 text-orange-600",
  competition_risk: "bg-yellow-50 border-yellow-200 text-yellow-600",
  macro_risk: "bg-gray-50 border-gray-200 text-gray-500",
  insider_selling: "bg-purple-50 border-purple-200 text-purple-600",
};

function FilingCard({ filing }: { filing: SecFiling }) {
  const [open, setOpen] = useState(false);
  const s = filing.ai_summary;
  const flags = filing.risk_flags ?? [];

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 space-y-2">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="font-semibold text-gray-800 text-sm">{filing.form_type}</span>
          <span className="text-xs text-gray-400 ml-2">{filing.filed_date}</span>
          {filing.report_period && (
            <span className="text-xs text-gray-300 ml-1">({filing.report_period} 기준)</span>
          )}
          {filing.edgar_url && (
            <a
              href={filing.edgar_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-blue-400 hover:text-blue-600 ml-2"
            >
              EDGAR ↗
            </a>
          )}
        </div>
        {flags.length > 0 && (
          <span className="text-xs bg-red-50 border border-red-200 text-red-500 rounded-full px-2 py-0.5 shrink-0">
            리스크 {flags.length}건
          </span>
        )}
      </div>

      {/* 리스크 플래그 뱃지 */}
      {flags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {flags.map((f) => (
            <span key={f} className={`text-[10px] px-2 py-0.5 rounded-full border ${RISK_COLOR[f] ?? "bg-gray-50 border-gray-200 text-gray-500"}`}>
              {RISK_LABEL[f] ?? f}
            </span>
          ))}
        </div>
      )}

      {/* AI 요약 토글 */}
      {s && (
        <>
          <button
            onClick={() => setOpen((o) => !o)}
            className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
          >
            <span>{open ? "▾" : "▸"}</span>
            <span>AI 분석 {open ? "접기" : "보기"}</span>
          </button>
          {open && (
            <div className="space-y-2 pt-1 border-t border-gray-50">
              {s.performance_summary && (
                <div>
                  <div className="text-[10px] font-semibold text-gray-400 mb-0.5">실적</div>
                  <p className="text-xs text-gray-700 leading-relaxed">{s.performance_summary}</p>
                </div>
              )}
              {s.risk_summary && (
                <div>
                  <div className="text-[10px] font-semibold text-gray-400 mb-0.5">리스크</div>
                  <p className="text-xs text-gray-700 leading-relaxed">{s.risk_summary}</p>
                </div>
              )}
              {s.guidance_summary && (
                <div>
                  <div className="text-[10px] font-semibold text-gray-400 mb-0.5">가이던스</div>
                  <p className="text-xs text-gray-700 leading-relaxed">{s.guidance_summary}</p>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function SecReportTab({ ticker }: { ticker: string }) {
  const [filings, setFilings] = useState<SecFiling[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${SEC_API}/${ticker}`)
      .then((r) => {
        if (!r.ok) throw new Error(`조회 실패 (${r.status})`);
        return r.json();
      })
      .then((data) => setFilings(Array.isArray(data) ? data : []))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) return (
    <div className="flex justify-center pt-10">
      <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (error) return (
    <div className="text-center pt-8">
      <p className="text-gray-500 text-sm">{error}</p>
      <p className="text-xs text-gray-400 mt-1">EDGAR API 조회 실패 — 잠시 후 다시 시도하세요.</p>
    </div>
  );

  if (filings.length === 0) return (
    <div className="text-center pt-8">
      <p className="text-gray-400 text-sm">SEC 파일링 없음</p>
      <p className="text-xs text-gray-300 mt-1">EDGAR에 등록된 파일링이 없거나 티커를 찾을 수 없습니다.</p>
    </div>
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400">최근 {filings.length}건 · EDGAR 원문 링크 포함</p>
      {filings.map((f) => <FilingCard key={f.id} filing={f} />)}
    </div>
  );
}
