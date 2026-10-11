"use client";
import { useWatchlist } from "@/lib/useWatchlist";

export default function StarButton({ code }: { code: string }) {
  const { has, toggle, ready } = useWatchlist();
  const on = ready && has(code);
  return (
    <button
      type="button"
      className={`star ${on ? "on" : ""}`}
      aria-pressed={on}
      aria-label={on ? `Hapus ${code} dari watchlist` : `Tambah ${code} ke watchlist`}
      onClick={(e) => { e.stopPropagation(); toggle(code); }}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
