import { NextRequest, NextResponse } from "next/server";

const BACKEND =
  process.env.SUPPLY_API_URL ??
  process.env.NEXT_PUBLIC_SUPPLY_API_URL ??
  "http://168.107.52.56:8000";

async function proxy(req: NextRequest, segments: string[]) {
  const path = segments.join("/");
  const { searchParams } = new URL(req.url);
  const qs = searchParams.toString();
  const url = `${BACKEND}/supply/${path}${qs ? `?${qs}` : ""}`;

  try {
    const res = await fetch(url, { method: req.method });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json({ detail: String(e) }, { status: 502 });
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path);
}
