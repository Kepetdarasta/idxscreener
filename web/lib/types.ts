export type PricePoint = { d: string; close: number };
export type PhaseBand = { phase: string; from: string; to: string };
export type TradeSetup = { entry: number; stop: number; target: number; rr: number; date: string };
export type Levels = { support: number; resistance: number };
export type CheckItem = { label: string; ok: boolean | null; detail: string };

export type StockRow = {
  code: string; name: string; sector: string | null;
  phase: string | null; score: number | null;
  close: number | null; chg: number | null; rr: number | null;
};

export type PhaseRow = {
  phase: string; start: string; end: string | null; days: number | null;
  priceStart: number; priceEnd: number | null; changePct: number | null;
};

export type StockDetailData = {
  code: string; name: string; sector: string | null;
  last: { d: string; close: number; chg: number | null };
  signal: { phase: string; score: number } | null;
  setup: TradeSetup | null;
  levels: Levels | null;
  prices: PricePoint[]; bands: PhaseBand[];
  checklist: CheckItem[];
  history: PhaseRow[];
};
