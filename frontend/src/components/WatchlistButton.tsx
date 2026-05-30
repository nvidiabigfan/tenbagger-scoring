"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

interface Props {
  ticker: string;
}

export default function WatchlistButton({ ticker }: Props) {
  const router = useRouter();
  const [inWl, setInWl] = useState(false);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      const u = data.session?.user ?? null;
      setUserId(u?.id ?? null);
      if (u) {
        const { data: row } = await supabase
          .from("watchlist")
          .select("ticker")
          .eq("user_id", u.id)
          .eq("ticker", ticker)
          .maybeSingle();
        setInWl(!!row);
      }
      setReady(true);
    });
  }, [ticker]);

  const toggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!userId) { router.push("/login"); return; }
    setLoading(true);
    if (inWl) {
      await supabase.from("watchlist").delete().eq("ticker", ticker).eq("user_id", userId);
      setInWl(false);
    } else {
      await supabase.from("watchlist").upsert(
        { user_id: userId, ticker, alert_enabled: true, alert_threshold: 10.0 },
        { onConflict: "user_id,ticker", ignoreDuplicates: true }
      );
      setInWl(true);
    }
    setLoading(false);
  };

  if (!ready) return <span className="w-6 h-6 inline-block" />;

  return (
    <button
      onClick={toggle}
      disabled={loading}
      title={inWl ? "워치리스트에서 제거" : "워치리스트에 추가"}
      className={`
        w-6 h-6 flex items-center justify-center rounded transition-colors text-base leading-none
        ${inWl
          ? "text-yellow-400 hover:text-gray-300"
          : "text-gray-200 hover:text-yellow-400"
        }
        ${loading ? "opacity-50 cursor-wait" : "cursor-pointer"}
      `}
    >
      {inWl ? "★" : "☆"}
    </button>
  );
}
