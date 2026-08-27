import { describe, expect, it, vi } from "vitest";
import {
  deterministicTradeoffNarrative,
  guardedTradeoffNarrative,
  narrativeUsesOnlyPayloadNumerals,
  requestTradeoffNarrative,
  type TradeoffPayload,
} from "./tradeoff-narrative";

const payload: TradeoffPayload = {
  regionA: { id: 10, name: "North Example" },
  regionB: { id: 20, name: "South Example" },
  maxPurchasePriceDelta: "$125,000",
  medianHomeValueDelta: "$80,000",
  commuteMinutesDelta: "12.5 min",
  topMetricGaps: [{ label: "Tree coverage", regionAValue: "62.0%", regionBValue: "38.0%" }],
  profileBucket: "budget-5500-good",
};

describe("tradeoff narrative guard", () => {
  it("accepts numerals already present in the structured payload", () => {
    expect(
      narrativeUsesOnlyPayloadNumerals(
        "North Example offers $125,000 more reach, with a 12.5 min drive-time difference.",
        payload,
      ),
    ).toBe(true);
  });

  it("catches an injected hallucinated number and uses the deterministic template", () => {
    const result = guardedTradeoffNarrative(
      "North Example is 17 minutes faster and offers $125,000 more reach.",
      payload,
    );
    expect(result.source).toBe("template");
    expect(result.narrative).toBe(deterministicTradeoffNarrative(payload));
    expect(result.narrative).not.toContain("17");
  });

  it("guards the live API response before returning it", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          content: [{ type: "text", text: "The commute difference is 99 minutes." }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const result = await requestTradeoffNarrative(payload, { apiKey: "test", fetcher });
    expect(result.source).toBe("template");
    expect(result.narrative).not.toContain("99");
  });
});
