"use client";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceArea, ResponsiveContainer,
} from "recharts";
import { phaseOf } from "@/lib/phases";

export type PricePoint = { d: string; close: number };
export type PhaseBand = { phase: string; from: string; to: string };

export default function PhaseChart({ prices, bands }: { prices: PricePoint[]; bands: PhaseBand[] }) {
  return (
    <ResponsiveContainer width="100%" height={380}>
      <LineChart data={prices} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        {bands.map((b, i) => (
          <ReferenceArea key={i} x1={b.from} x2={b.to} fill={phaseOf(b.phase).color} fillOpacity={0.16} />
        ))}
        <XAxis dataKey="d" tick={{ fontSize: 12 }} minTickGap={40} />
        <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12 }} width={56} />
        <Tooltip formatter={(v: number) => v.toLocaleString("id-ID")} />
        <Line type="monotone" dataKey="close" stroke="#1d2433" dot={false} strokeWidth={1.8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
