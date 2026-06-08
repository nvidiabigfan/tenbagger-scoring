"use client";

import { useEffect, useState } from "react";

interface DebateData {
  available: boolean;
  ticker?: string;
  bull_text?: string;
  bear_text?: string;
  score_at_gen?: number;
  signal_at_gen?: string;
  generated_at?: string;
}

export default function DebateTab({ ticker, inWatchlist, onAddWatchlist }: {
  ticker: string;
  inWatchlist: boolean;
  onAddWatchlist: () => void;
}) {
  const [data, setData] = useState<DebateData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/debate/${ticker}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ available: false }))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <div className="w-8 h-8 border-4 border-blue-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!data?.available) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 text-center">
        <p className="text-gray-500 text-sm mb-1">
          {inWatchlist
            ? "토론 리포트가 아직 생성되지 않았습니다."
            : "워치리스트에 추가하면 강세·약세 토론 리포트가 생성됩니다."}
        </p>
        <p className="text-gray-400 text-xs mb-4">
          {inWatchlist
            ? "다음 배치(KST 03:00) 실행 후 노출됩니다."
            : "다음 배치 실행 시 점수 변동이 있으면 자동 생성됩니다."}
        </p>
        {!inWatchlist && (
          <button
            onClick={onAddWatchlist}
            className="text-xs px-3 py-1.5 rounded-lg border border-blue-300 text-blue-600 bg-blue-50 hover:bg-blue-100 transition-colors"
          >
            ★ 워치리스트에 추가
          </button>
        )}
      </div>
    );
  }

  const genDate = data.generated_at
    ? new Date(data.generated_at).toLocaleString("ko-KR", {
        month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : null;

  return (
    <div className="space-y-3">
      {/* 강세·약세 2단 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* 강세 */}
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="text-base">🟢</span>
            <span className="text-sm font-bold text-green-700">강세론</span>
          </div>
          <p className="text-xs text-green-900 leading-relaxed whitespace-pre-wrap">
            {data.bull_text}
          </p>
        </div>

        {/* 약세 */}
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="text-base">🔴</span>
            <span className="text-sm font-bold text-red-700">약세론</span>
          </div>
          <p className="text-xs text-red-900 leading-relaxed whitespace-pre-wrap">
            {data.bear_text}
          </p>
        </div>
      </div>

      {/* 메타 + 면책 */}
      <div className="text-center space-y-1">
        {genDate && data.score_at_gen !== undefined && (
          <p className="text-[10px] text-gray-400">
            생성일 {genDate} · 생성 시점 점수 {Number(data.score_at_gen).toFixed(1)}점
          </p>
        )}
        <p className="text-[10px] text-gray-300">
          본 서비스는 투자 자문이 아니며 참고용입니다.
        </p>
      </div>
    </div>
  );
}
