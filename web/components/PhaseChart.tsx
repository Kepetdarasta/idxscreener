"use client";
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { phaseOf } from "@/lib/phases";
import type { Levels, PhaseBand, PricePoint, TradeSetup } from "@/lib/types";

const TICK = { fontSize: 11, fill: "#8b9bb0" };

export default function PhaseChart({
  prices, bands, setup, levels, height = 300,
}: { prices: PricePoint[]; bands: PhaseBand[]; setup?: TradeSetup | null; levels?: Levels | null; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={prices} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1c2a3a" strokeDasharray="3 3" vertical={false} />
        {bands.map((b, i) => (
          <ReferenceArea key={i} x1={b.from} x2={b.to} fill={phaseOf(b.phase).color} fillOpacity={0.16} />
        ))}
        {setup && (
          <ReferenceLine y={setup.target} stroke="#3fb97f" strokeDasharray="5 4" ifOverflow="extendDomain"
            label={{ value: "Target", position: "insideTopRight", fontSize: 11, fill: "#3fb97f" }} />
        )}
        {setup && (
          <ReferenceLine y={setup.entry} stroke="#4a9eff" strokeDasharray="5 4" ifOverflow="extendDomain"
            label={{ value: "Entry", position: "insideTopRight", fontSize: 11, fill: "#4a9eff" }} />
        )}
        {setup && (
          <ReferenceLine y={setup.stop} stroke="#e5564b" strokeDasharray="5 4" ifOverflow="extendDomain"
            label={{ value: "Stop", position: "insideBottomRight", fontSize: 11, fill: "#e5564b" }} />
        )}
        {!setup && levels && (
          <ReferenceLine y={levels.resistance} stroke="#8b9bb0" strokeDasharray="2 4" ifOverflow="extendDomain"
            label={{ value: "Resistance", position: "insideTopRight", fontSize: 11, fill: "#8b9bb0" }} />
        )}
        {!setup && levels && (
          <ReferenceLine y={levels.support} stroke="#8b9bb0" strokeDasharray="2 4" ifOverflow="extendDomain"
            label={{ value: "Support", position: "insideBottomRight", fontSize: 11, fill: "#8b9bb0" }} />
        )}
        <XAxis dataKey="d" tick={TICK} stroke="#243447" minTickGap={48} />
        <YAxis domain={["auto", "auto"]} tick={TICK} stroke="#243447" width={56} />
        <Tooltip
          formatter={(v) => Number(v).toLocaleString("id-ID")}
          contentStyle={{ background: "#131d29", border: "1px solid #243447", borderRadius: 6, color: "#e7edf4", fontSize: 12 }}
          labelStyle={{ color: "#8b9bb0" }}
        />
        <Line type="monotone" dataKey="close" name="Penutupan" stroke="#e7edf4" dot={false} strokeWidth={1.8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
