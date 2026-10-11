import { NextResponse } from "next/server";
import { getStockRows } from "@/lib/data";

export async function GET(req: Request) {
  const codes = (new URL(req.url).searchParams.get("codes") ?? "")
    .split(",").map((s) => s.trim().toUpperCase())
    .filter((c) => /^[A-Z0-9]{1,10}$/.test(c)).slice(0, 60);
  const { rows } = await getStockRows();
  return NextResponse.json(rows.filter((r) => codes.includes(r.code)),
    { headers: { "Cache-Control": "public, s-maxage=900, stale-while-revalidate=3600" } });
}
