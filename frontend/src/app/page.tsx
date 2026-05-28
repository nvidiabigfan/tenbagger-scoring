"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

interface Stock {
  ticker: string;
  company_name: string;
  sector: string;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Stock[]>([]);
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (query.length < 1) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    supabase
      .from("stocks")
      .select("ticker, company_name, sector")
      .or(`ticker.ilike.${query.toUpperCase()}%,company_name.ilike.%${query}%`)
      .limit(8)
      .then(({ data }) => {
        setSuggestions(data ?? []);
        setOpen(true);
      });
  }, [query]);

  const go = (ticker: string) => {
    setOpen(false);
    router.push(`/analyze/${ticker.toUpperCase().trim()}`);
  };

  return (
    <div className="flex flex-col items-center pt-20">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">텐배거스코어링</h1>
      <p className="text-gray-500 mb-10 text-center text-sm">
        매출·ETF·애널리스트·시총·모멘텀·버즈·내부자 7개 모듈로 성장주 모멘텀 점수 0~100점
      </p>

      <div className="relative w-full max-w-md">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) go(query);
          }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder="NVDA, AAPL, BRK.B ..."
          className="w-full px-4 py-3 text-base border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          autoComplete="off"
        />

        {open && suggestions.length > 0 && (
          <ul className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
            {suggestions.map((s) => (
              <li
                key={s.ticker}
                onMouseDown={() => go(s.ticker)}
                className="px-4 py-3 cursor-pointer hover:bg-gray-50 flex justify-between items-center"
              >
                <span className="font-semibold text-gray-900 text-sm">{s.ticker}</span>
                <span className="text-xs text-gray-400 truncate ml-4 max-w-48">{s.company_name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button
        onClick={() => query.trim() && go(query)}
        className="mt-4 px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-medium transition-colors"
      >
        분석하기
      </button>

      <div className="mt-16 flex gap-3 flex-wrap justify-center">
        {["NVDA", "AAPL", "MSFT", "TSLA", "META", "AMZN"].map((t) => (
          <button
            key={t}
            onClick={() => go(t)}
            className="px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg text-gray-600 hover:border-blue-300 hover:text-blue-600 transition-colors"
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}
