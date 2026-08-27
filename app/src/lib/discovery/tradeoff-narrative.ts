import { z } from "zod";

const MetricGapSchema = z.object({
  label: z.string().min(1).max(80),
  regionAValue: z.string().min(1).max(40),
  regionBValue: z.string().min(1).max(40),
});

export const TradeoffPayloadSchema = z.object({
  regionA: z.object({ id: z.number().int().positive(), name: z.string().min(1).max(120) }),
  regionB: z.object({ id: z.number().int().positive(), name: z.string().min(1).max(120) }),
  maxPurchasePriceDelta: z.string().min(1).max(40),
  medianHomeValueDelta: z.string().min(1).max(40).nullable(),
  commuteMinutesDelta: z.string().min(1).max(40).nullable(),
  topMetricGaps: z.array(MetricGapSchema).max(4),
  profileBucket: z.string().min(1).max(160),
});

export type TradeoffPayload = z.infer<typeof TradeoffPayloadSchema>;

const numeralPattern = /[-+]?\d[\d,]*(?:\.\d+)?/g;

export function extractNormalizedNumerals(value: string) {
  return (value.match(numeralPattern) ?? []).map(normalizeNumeral);
}

function normalizeNumeral(value: string) {
  const parsed = Number(value.replaceAll(",", ""));
  return Number.isFinite(parsed) ? String(parsed) : value;
}

export function narrativeUsesOnlyPayloadNumerals(narrative: string, payload: TradeoffPayload) {
  const allowed = new Set(extractNormalizedNumerals(JSON.stringify(payload)));
  return extractNormalizedNumerals(narrative).every((value) => allowed.has(value));
}

export function deterministicTradeoffNarrative(payload: TradeoffPayload) {
  const price = `${payload.regionA.name}'s estimated max home price differs from ${payload.regionB.name}'s by ${payload.maxPurchasePriceDelta}`;
  const details = [
    payload.medianHomeValueDelta
      ? `their district median home values differ by ${payload.medianHomeValueDelta}`
      : null,
    payload.commuteMinutesDelta
      ? `the modeled drive-time difference is ${payload.commuteMinutesDelta}`
      : null,
    payload.topMetricGaps[0]
      ? `${payload.topMetricGaps[0].label} is ${payload.topMetricGaps[0].regionAValue} versus ${payload.topMetricGaps[0].regionBValue}`
      : null,
  ].filter((value): value is string => value !== null);
  return `${price}${details.length ? `; ${details.join(", and ")}` : ""}. Compare these district-level estimates with the listing details that matter most to you.`;
}

export function guardedTradeoffNarrative(candidate: string, payload: TradeoffPayload) {
  const trimmed = candidate.trim();
  if (!trimmed || !narrativeUsesOnlyPayloadNumerals(trimmed, payload)) {
    return { narrative: deterministicTradeoffNarrative(payload), source: "template" as const };
  }
  return { narrative: trimmed, source: "claude" as const };
}

export async function requestTradeoffNarrative(
  payloadInput: TradeoffPayload,
  options: { apiKey: string; model?: string; fetcher?: typeof fetch },
) {
  const payload = TradeoffPayloadSchema.parse(payloadInput);
  const fetcher = options.fetcher ?? fetch;
  const model = options.model ?? "claude-sonnet-4-20250514";
  const response = await fetcher("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": options.apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: 220,
      temperature: 0,
      messages: [
        {
          role: "user",
          content:
            "Write one neutral paragraph comparing these two school districts for a home search. " +
            "Use only the supplied facts. Every numeral in your response must appear verbatim in " +
            `the JSON payload. Do not invent causality or address-level claims.\n${JSON.stringify(payload)}`,
        },
      ],
    }),
  });
  if (!response.ok) throw new Error(`Anthropic narrative request failed (${response.status})`);
  const body = (await response.json()) as { content?: Array<{ type?: string; text?: string }> };
  const candidate = (body.content ?? [])
    .filter((block) => block.type === "text")
    .map((block) => block.text ?? "")
    .join("");
  return { ...guardedTradeoffNarrative(candidate, payload), model };
}
