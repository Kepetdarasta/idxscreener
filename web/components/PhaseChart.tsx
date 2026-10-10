"use client";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceArea, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { phaseOf } from "@/lib/phases";

export type PricePoint = { d: string; close: number };
export type PhaseBand = { phase: string; from: string; to: string };
export type TradeSetup = { entry: number; stop: number; target: number };

export default function PhaseChart({
  prices, bands, setup,
}: { prices: PricePoint[]; bands: PhaseBand[]; setup?: TradeSetup | null }) {
  return (
    <ResponsiveContainer width="100%" height={380}>
      <LineChart data={prices} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        {bands.map((b, i) => (
          <ReferenceArea key={i} x1={b.from} x2={b.to} fill={phaseOf(b.phase).color} fillOpacity={0.16} />
        ))}
        {setup && (
          <ReferenceLine y={setup.target} stroke="#2f8f5b" strokeDasharray="5 4" ifOverflow="extendDomain"
            label={{ value: "Target", position: "insideTopRight", fontSize: 12 }} />
        )}
        {setup && (
          <ReferenceLine y={setup.entry} stroke="#2f6fb5" strokeDasharray="5 4" ifOverflow="extendDomain"
            label={{ value: "Entry", position: "insideTopRight", fontSize: 12 }} />
        )}
        {setup && (
          <ReferenceLine y={setup.stop} stroke="#c0392b" strokeDasharray="5 4" ifOverflow="extendDomain"
            label={{ value: "Stop", position: "insideBottomRight", fontSize: 12 }} />
        )}
        <XAxis dataKey="d" tick={{ fontSize: 12 }} minTickGap={40} />
        <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12 }} width={56} />
        <Tooltip formatter={(v) => Number(v).toLocaleString("id-ID")} />
        <Line type="monotone" dataKey="close" stroke="#1d2433" dot={false} strokeWidth={1.8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
