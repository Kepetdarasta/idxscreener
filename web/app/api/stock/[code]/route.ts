import { NextResponse } from "next/server";
import { getStockDetail } from "@/lib/data";

export async function GET(_req: Request, { params }: { params: Promise<{ code: string }> }) {
  const data = await getStockDetail((await params).code);
  if (!data) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(data, { headers: { "Cache-Control": "public, s-maxage=900, stale-while-revalidate=3600" } });
}
