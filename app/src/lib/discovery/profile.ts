export function parseDollarAmount(value: string, fallback: number, allowZero = false) {
  const normalized = value.replace(/[$,\s]/g, "");
  if (!normalized) return fallback;
  const parsed = Number(normalized);
  const isValid = Number.isFinite(parsed) && (allowZero ? parsed >= 0 : parsed > 0);
  return isValid ? parsed : fallback;
}
