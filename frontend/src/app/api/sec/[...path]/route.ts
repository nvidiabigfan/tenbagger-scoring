import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.SUPPLY_API_URL ?? "http://168.107.52.56:8010";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const url = `${BACKEND}/sec/${path.join("/")}`;
  try {
    const res = await fetch(url, { next: { revalidate: 3600 } });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json({ detail: String(e) }, { status: 502 });
  }
}
