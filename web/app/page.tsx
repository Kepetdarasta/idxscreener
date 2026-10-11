import ScreenerClient from "@/components/ScreenerClient";
import { getStockRows } from "@/lib/data";

export const revalidate = 900; // data baru masuk sekali per hari; cache 15 menit cukup

export default async function Home() {
  const { rows, screenDate } = await getStockRows();
  return (
    <main className="wide">
      <h1>Siklus saham</h1>
      <p className="muted lead">Fase akumulasi, mark up, distribusi, dan mark down dari pola harga dan volume. Hanya saham yang sinyalnya terdeteksi pada penutupan terakhir.</p>
      <ScreenerClient rows={rows.filter((r) => r.phase)} date={screenDate} />
    </main>
  );
}
