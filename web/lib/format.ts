export const idr = (n: number | null | undefined) =>
  n == null ? "–" : n.toLocaleString("id-ID", { maximumFractionDigits: 0 });

export const pct = (n: number | null | undefined, d = 2) =>
  n == null ? "–" : `${n > 0 ? "+" : ""}${n.toFixed(d)}%`;
