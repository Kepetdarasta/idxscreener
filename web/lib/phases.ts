export const PHASES = {
  accumulation: { label: "Akumulasi", color: "#3fb97f" },
  markup: { label: "Mark Up", color: "#4a9eff" },
  distribution: { label: "Distribusi", color: "#e89a3c" },
  markdown: { label: "Mark Down", color: "#e5564b" },
  unknown: { label: "Belum jelas", color: "#7c8aa0" },
} as const;

export type PhaseKey = keyof typeof PHASES;
export const PHASE_ORDER = ["accumulation", "markup", "distribution", "markdown"] as const;
export const phaseOf = (p: string | null | undefined) => PHASES[(p ?? "") as PhaseKey] ?? PHASES.unknown;
