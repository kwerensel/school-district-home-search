import { DEFAULT_ANNUAL_RATE } from "./purchasing-power";

export const PMMS_CSV_URL =
  "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US&cosd=2025-01-01";
export const RATE_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export type MortgageRateSource = "pmms" | "fallback" | "user";

export type MortgageRateAssumption = {
  annualRate: number;
  source: MortgageRateSource;
  observationDate: string | null;
};

let cachedRate: (MortgageRateAssumption & { fetchedAt: number }) | null = null;

export function parsePmmsCsv(csv: string): MortgageRateAssumption {
  const observations = csv
    .trim()
    .split(/\r?\n/)
    .slice(1)
    .map((line) => {
      const [observationDate, rawRate] = line.split(",");
      return { observationDate, percentRate: Number(rawRate) };
    })
    .filter(
      (row) =>
        /^\d{4}-\d{2}-\d{2}$/.test(row.observationDate ?? "") &&
        Number.isFinite(row.percentRate) &&
        row.percentRate > 0 &&
        row.percentRate < 25,
    );
  const latest = observations.at(-1);
  if (!latest) throw new Error("PMMS response contained no valid observations");
  return {
    annualRate: latest.percentRate / 100,
    source: "pmms",
    observationDate: latest.observationDate,
  };
}

export async function getMortgageRateAssumption({
  fetchImpl = fetch,
  now = Date.now,
  timeoutMs = 3000,
}: {
  fetchImpl?: typeof fetch;
  now?: () => number;
  timeoutMs?: number;
} = {}): Promise<MortgageRateAssumption> {
  const currentTime = now();
  if (cachedRate && currentTime - cachedRate.fetchedAt < RATE_CACHE_TTL_MS) {
    const { fetchedAt: _fetchedAt, ...assumption } = cachedRate;
    return assumption;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(PMMS_CSV_URL, {
      headers: { Accept: "text/csv" },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`PMMS request failed with ${response.status}`);
    const assumption = parsePmmsCsv(await response.text());
    cachedRate = { ...assumption, fetchedAt: currentTime };
    return assumption;
  } catch {
    return {
      annualRate: DEFAULT_ANNUAL_RATE,
      source: "fallback",
      observationDate: null,
    };
  } finally {
    clearTimeout(timeout);
  }
}

export function clearMortgageRateCacheForTests() {
  cachedRate = null;
}
