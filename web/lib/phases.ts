export const PHASES = {
  accumulation: { label: "Akumulasi", color: "#2f8f5b" },
  markup: { label: "Mark Up", color: "#2f6fb5" },
  distribution: { label: "Distribusi", color: "#d9822b" },
  markdown: { label: "Mark Down", color: "#c0392b" },
  unknown: { label: "Belum jelas", color: "#8a8f98" },
} as const;

export type PhaseKey = keyof typeof PHASES;
export const phaseOf = (p: string) => PHASES[p as PhaseKey] ?? PHASES.unknown;
