import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

function getServiceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL/SUPABASE_SERVICE_KEY env not configured");
  return createClient(url, key);
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { ticker: string } }
) {
  const ticker = params.ticker.toUpperCase().replace(/[^A-Z.]/g, "").slice(0, 6);
  if (!ticker) return NextResponse.json({ error: "invalid ticker" }, { status: 400 });

  try {
    const { data, error } = await getServiceClient()
      .from("debates")
      .select("ticker, bull_text, bear_text, score_at_gen, signal_at_gen, generated_at")
      .eq("ticker", ticker)
      .maybeSingle();

    if (error) throw error;
    if (!data) return NextResponse.json({ available: false });

    return NextResponse.json({ available: true, ...data });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
