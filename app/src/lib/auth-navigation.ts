export function safeReturnTo(value: string | null, fallback = "/saved") {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return fallback;
  return value;
}
