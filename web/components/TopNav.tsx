"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Siklus ADMD" },
  { href: "/all", label: "Semua saham" },
  { href: "/cross-ma", label: "Cross MA" },
  { href: "/kombinasi", label: "Kombinasi" },
  { href: "/heatmap", label: "Heatmap sektor" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/panduan", label: "Panduan" },
];

export default function TopNav() {
  const p = usePathname();
  const active = (h: string) => (h === "/" ? p === "/" || p.startsWith("/stocks") : p.startsWith(h));
  return (
    <nav className="tabs" aria-label="Menu utama">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} aria-current={active(t.href) ? "page" : undefined}>{t.label}</Link>
      ))}
    </nav>
  );
}
