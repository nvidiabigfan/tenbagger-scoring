"use client";

import { useEffect, useState } from "react";

const SUPPLY_API = "/api/supply";

interface SupplySnapshot {
  ticker: string;
  snapshot_date: string;
  institutional_net: number | null;
  insider_net: number | null;
  short_interest_pct: number | null;
  pc_ratio: number | null;
  volume_vs_avg: number | null;
  close_price: number | null;
  source_flags: Record<string, boolean>;
}

interface HistoryItem {
  snapshot_date: string;
  close_price: number | null;
  short_interest_pct: number | null;
  pc_ratio: number | null;
  volume_vs_avg: number | null;
}

function MiniChart({
  data,
  color,
  refLine,
  pct,
}: {
  data: { x: string; y: number | null }[];
  color: string;
  refLine?: number;
  pct?: boolean;
}) {
  const vals = data.map((d) => d.y).filter((v): v is number => v !== null);
  if (vals.length < 2) return <div className="h-16 flex items-center justify-center text-xs text-gray-300">데이터 부족</div>;

  const W = 300, H = 60, PAD = 6;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const toY = (v: number) => PAD + (H - PAD * 2) * (1 - (v - min) / range);
  const toX = (i: number) => PAD + (i / (vals.length - 1)) * (W - PAD * 2);

  const pts = vals.map((v, i) => `${toX(i)},${toY(v)}`).join(" ");
  const areaPath =
    `M ${toX(0)},${H} ` +
    vals.map((v, i) => `L ${toX(i)},${toY(v)}`).join(" ") +
    ` L ${toX(vals.length - 1)},${H} Z`;

  const refY = refLine !== undefined ? toY(Math.max(min, Math.min(max, refLine))) : null;

  const last = vals[vals.length - 1];
  const fmt = pct ? `${last.toFixed(1)}%` : last.toFixed(2);

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ height: 60 }}>
        <defs>
          <linearGradient id={`g-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.15" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#g-${color})`} />
        {refY !== null && (
          <line x1={PAD} y1={refY} x2={W - PAD} y2={refY} stroke={color} strokeWidth="1" strokeDasharray="4,3" opacity="0.4" />
        )}
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={toX(vals.length - 1)} cy={toY(last)} r="3.5" fill={color} />
      </svg>
      <div className="flex justify-between text-[10px] text-gray-300 px-1 -mt-1">
        <span>{data[0]?.x?.slice(5)}</span>
        <span className="font-semibold" style={{ color }}>{fmt}</span>
        <span>{data[data.length - 1]?.x?.slice(5)}</span>
      </div>
    </div>
  );
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="text-[10px] text-gray-400 mb-0.5">{label}</div>
      <div className="text-lg font-bold text-gray-800">{value}</div>
      {sub && <div className="text-[10px] text-gray-400">{sub}</div>}
    </div>
  );
}

export default function SupplyTab({ ticker }: { ticker: string }) {
  const [snap, setSnap] = useState<SupplySnapshot | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [collecting, setCollecting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [snapRes, histRes] = await Promise.all([
        fetch(`${SUPPLY_API}/${ticker}`),
        fetch(`${SUPPLY_API}/${ticker}/history?limit=60`),
      ]);

      if (snapRes.status === 404) {
        setError("수급 데이터 없음");
        setLoading(false);
        return;
      }
      if (!snapRes.ok) throw new Error(`수급 조회 실패 (${snapRes.status})`);

      const [snapData, histData] = await Promise.all([snapRes.json(), histRes.json()]);
      setSnap(snapData);
      setHistory(Array.isArray(histData) ? histData.reverse() : []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [ticker]);

  const collect = async () => {
    setCollecting(true);
    try {
      await fetch(`${SUPPLY_API}/${ticker}/collect`, { method: "POST" });
      await load();
    } catch {
      setError("수집 실패");
    } finally {
      setCollecting(false);
    }
  };

  if (loading) return (
    <div className="flex justify-center pt-10">
      <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (error) return (
    <div className="text-center pt-8 space-y-3">
      <p className="text-gray-500 text-sm">{error}</p>
      <button
        onClick={collect}
        disabled={collecting}
        className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
      >
        {collecting ? "수집 중..." : "수급 데이터 수집"}
      </button>
    </div>
  );

  if (!snap) return null;

  const histMap = (key: keyof HistoryItem) =>
    history.map((h) => ({ x: h.snapshot_date, y: h[key] as number | null }));

  const shortPct = snap.short_interest_pct != null ? snap.short_interest_pct * 100 : null;

  return (
    <div className="space-y-3">
      {/* 메트릭 카드 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <MetricCard
          label="종가"
          value={snap.close_price != null ? `$${snap.close_price.toFixed(2)}` : "—"}
          sub={snap.snapshot_date}
        />
        <MetricCard
          label="공매도 비율"
          value={shortPct != null ? `${shortPct.toFixed(1)}%` : "—"}
          sub="FINRA 기준"
        />
        <MetricCard
          label="거래량 배수"
          value={snap.volume_vs_avg != null ? `${snap.volume_vs_avg.toFixed(2)}×` : "—"}
          sub="20일 평균 대비"
        />
        <MetricCard
          label="P/C 비율"
          value={snap.pc_ratio != null ? snap.pc_ratio.toFixed(2) : "—"}
          sub="1.0 = 중립"
        />
        <MetricCard
          label="기관 거래 변화"
          value={snap.institutional_net != null ? `${snap.institutional_net > 0 ? "+" : ""}${snap.institutional_net.toFixed(2)}%` : "—"}
          sub="Finviz 분기"
        />
        <MetricCard
          label="내부자 거래 변화"
          value={snap.insider_net != null ? `${snap.insider_net > 0 ? "+" : ""}${snap.insider_net.toFixed(2)}%` : "—"}
          sub="Finviz 분기"
        />
      </div>

      {/* 차트 */}
      {history.length >= 2 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="bg-white rounded-xl border border-gray-100 p-3">
            <div className="text-xs font-semibold text-gray-500 mb-2">종가 추이</div>
            <MiniChart data={histMap("close_price")} color="#3b82f6" />
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-3">
            <div className="text-xs font-semibold text-gray-500 mb-2">거래량 배수</div>
            <MiniChart data={histMap("volume_vs_avg")} color="#10b981" refLine={2} />
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-3">
            <div className="text-xs font-semibold text-gray-500 mb-2">공매도 비율 (%)</div>
            <MiniChart
              data={history.map((h) => ({ x: h.snapshot_date, y: h.short_interest_pct != null ? h.short_interest_pct * 100 : null }))}
              color="#f59e0b"
              refLine={10}
              pct
            />
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-3">
            <div className="text-xs font-semibold text-gray-500 mb-2">Put/Call 비율</div>
            <MiniChart data={histMap("pc_ratio")} color="#8b5cf6" refLine={1.0} />
          </div>
        </div>
      )}

      {/* 데이터 소스 */}
      <div className="flex flex-wrap gap-2 text-[10px]">
        {Object.entries(snap.source_flags ?? {}).map(([k, v]) => (
          <span key={k} className={`px-2 py-0.5 rounded-full border ${v ? "bg-green-50 border-green-200 text-green-600" : "bg-gray-50 border-gray-200 text-gray-400"}`}>
            {k}: {v ? "✓" : "✗"}
          </span>
        ))}
        <button onClick={collect} disabled={collecting} className="ml-auto text-blue-500 hover:text-blue-700 disabled:opacity-40">
          {collecting ? "수집 중..." : "↻ 새로고침"}
        </button>
      </div>
    </div>
  );
}
