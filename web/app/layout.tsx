import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import TopNav from "@/components/TopNav";
import { getIndexBar } from "@/lib/data";
import { pct } from "@/lib/format";

const font = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], display: "swap" });

export const metadata: Metadata = {
  title: "Siklus Saham IDX",
  description: "Screening fase siklus saham IDX dari harga dan volume (data akhir hari).",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const idx = await getIndexBar().catch(() => null);
  return (
    <html lang="id">
      <body className={font.className}>
        <header className="top">
          <div className="brand">
            <b>Siklus Saham IDX</b>
            <span className="muted">Data akhir hari · bukan real-time</span>
          </div>
          {idx && (
            <div className="idx" title={`IHSG per ${idx.date}`}>
              <small>IHSG</small>
              <b>{idx.close.toLocaleString("id-ID", { maximumFractionDigits: 2 })}</b>
              <span className={(idx.chg ?? 0) >= 0 ? "pos" : "neg"}>{pct(idx.chg)}</span>
            </div>
          )}
        </header>
        <TopNav />
        {children}
      </body>
    </html>
  );
}
