import Link from "next/link";
import { notFound } from "next/navigation";
import StockDetail from "@/components/StockDetail";
import { getStockDetail } from "@/lib/data";

export const revalidate = 900;

export default async function StockPage({ params }: { params: Promise<{ code: string }> }) {
  const data = await getStockDetail((await params).code);
  if (!data) notFound();
  return (
    <main>
      <p><Link href="/">← Kembali ke daftar</Link></p>
      <StockDetail data={data} full />
    </main>
  );
}
