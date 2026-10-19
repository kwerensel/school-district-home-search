import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DiscoveryEvidence } from "./DiscoveryEvidence";
import { useServerFn } from "@tanstack/react-start";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  converseWithDiscovery,
  getConversationAvailability,
  runDiscoveryAnalysis,
} from "@/lib/discovery/conversation.functions";
import { HousingScenarioSchema, OpportunityCostSchema } from "@/lib/finance/opportunity-cost";
import type {
  ConversationProfile,
  ConversationResult,
  Evidence,
} from "@/lib/discovery/conversation";

type Turn = { user: string; result: ConversationResult };
export function DiscoveryConversation({
  profile,
  onApply,
  districts,
}: {
  districts: Array<{ districtSlug: string; districtName: string }>;
  profile: ConversationProfile;
  onApply: (profile: ConversationProfile) => void;
}) {
  const converse = useServerFn(converseWithDiscovery);
  const checkAvailability = useServerFn(getConversationAvailability);
  const analyze = useServerFn(runDiscoveryAnalysis);
  const availability = useQuery({
    queryKey: ["discovery-conversation-availability"],
    queryFn: () => checkAvailability(),
    staleTime: 60000,
    retry: false,
  });
  const [comparison, setComparison] = useState(["", ""]);
  const [goals, setGoals] = useState<Array<"investing" | "business-flexibility" | "future-rental">>(
    [],
  );
  const [rentalUse, setRentalUse] = useState<"unspecified" | "long-term" | "short-term">(
    "unspecified",
  );
  const comparisonSlugs = comparison.filter(Boolean);
  const [analysis, setAnalysis] = useState<{ evidence: Evidence[]; signature: string } | null>(
    null,
  );

  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const [error, setError] = useState("");
  const [undo, setUndo] = useState<{
    before: ConversationProfile;
    after: ConversationProfile;
  } | null>(null);
  const [housingEnabled, setHousingEnabled] = useState(false);
  const [housing, setHousing] = useState({ purchasePrice: "", additionalMonthlyCosts: "" });
  const [scenarioEnabled, setScenarioEnabled] = useState(false);
  const [scenario, setScenario] = useState({
    monthlyContribution: "",
    upfrontCapital: "",
    years: "",
    annualReturn: "",
  });
  const signature = JSON.stringify({
    profile,
    comparison,
    goals,
    rentalUse,
    housing,
    scenario,
    housingEnabled,
    scenarioEnabled,
  });
  const currentProfile = useRef(profile);
  currentProfile.current = profile;

  function context() {
    if (comparisonSlugs.length !== new Set(comparisonSlugs).size) {
      setError("Choose different districts for the comparison.");
      return null;
    }
    if (
      comparisonSlugs.some((slug) => !districts.some((district) => district.districtSlug === slug))
    ) {
      setError(
        "A selected district is outside the current search. Update the comparison selection.",
      );
      return null;
    }
    const candidate = OpportunityCostSchema.safeParse({
      monthlyContribution:
        scenario.monthlyContribution === "" ? NaN : Number(scenario.monthlyContribution),
      upfrontCapital: scenario.upfrontCapital === "" ? NaN : Number(scenario.upfrontCapital),
      years: scenario.years === "" ? NaN : Number(scenario.years),
      annualReturn: scenario.annualReturn === "" ? NaN : Number(scenario.annualReturn) / 100,
    });
    if (scenarioEnabled && !candidate.success) {
      setError(
        "Complete all scenario assumptions: nonnegative cash amounts, a whole-year horizon from 1–50, and an assumed annual return from −50% to 30%.",
      );
      return;
    }
    const housingCandidate = HousingScenarioSchema.safeParse({
      purchasePrice: housing.purchasePrice === "" ? NaN : Number(housing.purchasePrice),
      additionalMonthlyCosts:
        housing.additionalMonthlyCosts === "" ? NaN : Number(housing.additionalMonthlyCosts),
    });
    if (housingEnabled && !housingCandidate.success) {
      setError(
        "Enter a positive purchase price and nonnegative additional monthly costs for the housing comparison.",
      );
      return;
    }
    return {
      profile: structuredClone(profile),
      comparisonSlugs,
      goals,
      rentalUse,
      ...(scenarioEnabled && candidate.success ? { opportunity: candidate.data } : {}),
      ...(housingEnabled && housingCandidate.success ? { housing: housingCandidate.data } : {}),
    };
  }

  async function runAnalysis(
    tool: "compare_regions" | "compare_housing_costs" | "opportunity_cost" | "rental_feasibility",
  ) {
    if (busy.current) return;
    const data = context();
    if (!data) return;
    if (tool === "compare_housing_costs" && !data.housing) {
      setError("Enable and complete the housing scenario fields first.");
      return;
    }
    if (tool === "opportunity_cost" && !data.opportunity) {
      setError("Enable and complete the investment assumptions first.");
      return;
    }
    const snapshot = signature;
    busy.current = true;
    setPending(true);
    setError("");
    try {
      const reply = await analyze({ data: { ...data, tool } });
      if (reply.status === "ok") setAnalysis({ evidence: reply.evidence, signature: snapshot });
      else setError(reply.message);
    } catch {
      setError("Analysis could not connect. Your search has not changed.");
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  async function send() {
    if (busy.current || !draft.trim() || !availability.data?.configured) return;
    const data = context();
    if (!data) return;
    const user = draft.trim();
    busy.current = true;
    setPending(true);
    setError("");
    try {
      const messages = turns.slice(-5).flatMap((turn) => [
        { role: "user" as const, content: turn.user },
        {
          role: "assistant" as const,
          content: `${turn.result.interpretation}\n${turn.result.question}`,
        },
      ]);
      const reply = await converse({
        data: {
          messages: [...messages, { role: "user", content: user }],
          ...data,
        },
      });
      if (reply.status !== "ok") {
        setError(reply.message);
        return;
      }
      setTurns((previous) => [...previous.slice(-4), { user, result: reply.result }]);
      setDraft("");
    } catch {
      setError("Conversation could not connect. Your search has not changed.");
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  const last = turns.at(-1);
  const canApply =
    last?.result.proposal && JSON.stringify(last.result.baseline) === JSON.stringify(profile);
  const canUndo = undo && JSON.stringify(undo.after) === JSON.stringify(profile);
  return (
    <section
      className="space-y-3 rounded-lg border border-border p-3"
      aria-label="Conversational Discovery"
    >
      <h2 className="text-sm font-semibold">Talk through your search</h2>
      <p className="text-xs text-muted-foreground">
        Describe what matters, explore a tradeoff, or discuss future plans. Applying a preview
        updates your search; what-if questions leave it unchanged.
      </p>
      <p className="text-xs text-muted-foreground">
        When conversation is enabled, your message and current search inputs are sent to Claude.
        Conversation stays in this page session and is excluded from shared search URLs. Avoid
        identifying details.
      </p>
      <div className="space-y-2 text-xs">
        <p role="status">
          {availability.isPending
            ? "Checking conversation availability…"
            : availability.data?.configured
              ? "Conversation configured. All analysis uses verified data and financial tools."
              : availability.isError
                ? "Conversation availability could not be checked. Data comparisons and scenarios remain available."
                : "Conversation unavailable until an API key is configured. Compare verified data and run scenarios without it."}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={availability.isFetching || pending}
          onClick={() => void availability.refetch()}
        >
          Recheck conversation
        </Button>
        <p>Outside research: not enabled. No search outside Groundtruth has been performed.</p>
      </div>
      <fieldset className="space-y-2 text-xs">
        <legend className="font-medium">Longer-term goals for this conversation</legend>
        {(
          [
            ["investing", "Leave room to invest"],
            ["business-flexibility", "Preserve flexibility for a business"],
            ["future-rental", "Keep a future rental option"],
          ] as const
        ).map(([goal, label]) => (
          <label key={goal} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={goals.includes(goal)}
              disabled={pending}
              onChange={(event) =>
                setGoals((previous) =>
                  event.target.checked
                    ? [...previous, goal]
                    : previous.filter((value) => value !== goal),
                )
              }
            />
            {label}
          </label>
        ))}
        <p className="text-muted-foreground">
          These goals guide the discussion and stay in this page session. They do not add an
          unverified neighborhood score.
        </p>
        {goals.includes("future-rental") && (
          <label className="block">
            Intended rental use
            <select
              className="mt-1 w-full rounded border bg-background p-2"
              value={rentalUse}
              disabled={pending}
              onChange={(event) => setRentalUse(event.target.value as typeof rentalUse)}
            >
              <option value="unspecified">Still exploring</option>
              <option value="long-term">Long-term lease</option>
              <option value="short-term">Short-term stays</option>
            </select>
          </label>
        )}
      </fieldset>
      <fieldset className="space-y-2 text-xs">
        <legend className="font-medium">Compare specific districts (optional)</legend>
        <p className="text-muted-foreground">
          Choose up to two districts, or leave both empty to use the top-ranked results.
        </p>
        {comparison.map((slug, index) => (
          <label key={index} className="block">
            District {index + 1}
            <select
              className="mt-1 w-full rounded border bg-background p-2"
              value={slug}
              disabled={pending}
              onChange={(event) =>
                setComparison((previous) =>
                  previous.map((value, i) => (i === index ? event.target.value : value)),
                )
              }
            >
              <option value="">No selection</option>
              {slug && !districts.some((district) => district.districtSlug === slug) && (
                <option value={slug}>Selection outside current search</option>
              )}
              {districts.map((district) => (
                <option key={district.districtSlug} value={district.districtSlug}>
                  {district.districtName}
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={pending}
        onClick={() => void runAnalysis("compare_regions")}
      >
        Compare verified district data
      </Button>
      {analysis && (
        <div className="space-y-2 border-t pt-3">
          <p className="text-xs font-medium">Data and scenario results — no model used</p>
          {analysis.signature !== signature && (
            <p className="text-xs text-muted-foreground">
              Inputs have changed. These results use the previous inputs; run again to refresh.
            </p>
          )}
          <DiscoveryEvidence evidence={analysis.evidence} />
        </div>
      )}
      {turns.map((turn, index) => (
        <div key={index} className="space-y-2 border-t pt-3">
          <p className="whitespace-pre-wrap text-sm">
            <span className="font-semibold">You: </span>
            {turn.user}
          </p>
          <p className="whitespace-pre-wrap text-sm">
            <span className="font-semibold">Assistant interpretation: </span>
            {turn.result.interpretation}
          </p>
          <DiscoveryEvidence evidence={turn.result.evidence} />
          {turn.result.question && <p className="text-sm font-medium">{turn.result.question}</p>}
          <p className="text-xs text-muted-foreground">
            Outside research: not performed. Rental demand and property permissions are unverified.
          </p>
        </div>
      ))}
      {last?.result.proposal && (
        <div className="space-y-2 rounded bg-muted p-2 text-xs">
          <p className="font-medium">Proposed search changes</p>
          {Object.entries(last.result.proposal.weights)
            .filter(
              ([key, value]) =>
                value !== last.result.baseline.weights[key as keyof typeof profile.weights],
            )
            .map(([key, value]) => (
              <p key={key}>
                {key}: {last.result.baseline.weights[key as keyof typeof profile.weights]} → {value}
              </p>
            ))}
          {last.result.proposal.regionGroup !== last.result.baseline.regionGroup && (
            <p>
              Region: {last.result.baseline.regionGroup} → {last.result.proposal.regionGroup}
            </p>
          )}
          <Button
            type="button"
            size="sm"
            disabled={!canApply || pending}
            onClick={() => {
              if (
                !last.result.proposal ||
                JSON.stringify(currentProfile.current) !== JSON.stringify(last.result.baseline)
              )
                return;
              const after = structuredClone(last.result.proposal);
              setUndo({ before: structuredClone(profile), after });
              onApply(after);
            }}
          >
            Apply preview to search
          </Button>
          {!canApply && <p>Your search has changed since this preview. Ask again to refresh it.</p>}
        </div>
      )}
      {canUndo && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => {
            if (undo) onApply(undo.before);
            setUndo(null);
          }}
        >
          Undo assistant change
        </Button>
      )}
      <details className="text-xs">
        <summary className="cursor-pointer">Optional same-price housing comparison</summary>
        <label className="my-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={housingEnabled}
            disabled={pending}
            onChange={(event) => setHousingEnabled(event.target.checked)}
          />
          Compare taxes and monthly costs across districts
        </label>
        <p className="mb-2 text-muted-foreground">
          Enter the same home price to isolate cost differences. Additional costs should include
          your maintenance, HOA, and other monthly allowances. Area tax estimates cannot establish a
          particular property's bill.
        </p>
        {(
          [
            ["purchasePrice", "Purchase price ($)"],
            ["additionalMonthlyCosts", "Additional monthly costs ($)"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="mb-2 block">
            {label}
            <Input
              type="number"
              step="any"
              value={housing[key]}
              disabled={pending}
              onChange={(event) =>
                setHousing((previous) => ({ ...previous, [key]: event.target.value }))
              }
            />
          </label>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => void runAnalysis("compare_housing_costs")}
        >
          Calculate housing costs
        </Button>
        <p className="mt-2 text-muted-foreground">
          Select exactly two districts and enable investment assumptions to also model investing the
          cost difference.
        </p>
      </details>
      <details className="text-xs">
        <summary className="cursor-pointer">Optional investment scenario assumptions</summary>
        <label className="my-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={scenarioEnabled}
            disabled={pending}
            onChange={(event) => setScenarioEnabled(event.target.checked)}
          />
          Use these assumptions in the conversation
        </label>
        <p className="mb-2 text-muted-foreground">
          Hypothetical cash set aside or invested. Enter each assumption yourself. This does not
          calculate housing savings, rental income, or total wealth.
        </p>
        {(
          [
            ["monthlyContribution", "Monthly contribution ($)"],
            ["upfrontCapital", "Upfront capital ($)"],
            ["years", "Horizon (whole years)"],
            ["annualReturn", "Assumed annual return (%)"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="mb-2 block">
            {label}
            <Input
              type="number"
              step="any"
              value={scenario[key]}
              disabled={pending}
              onChange={(event) =>
                setScenario((previous) => ({ ...previous, [key]: event.target.value }))
              }
            />
          </label>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={pending}
          onClick={() => void runAnalysis("opportunity_cost")}
        >
          Calculate investment scenario
        </Button>
      </details>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={pending}
        onClick={() => void runAnalysis("rental_feasibility")}
      >
        What evidence is needed for rental use?
      </Button>
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label htmlFor="discovery-message" className="text-xs font-medium">
          Your preferences or question
        </label>
        <textarea
          id="discovery-message"
          rows={3}
          maxLength={4000}
          className="w-full rounded border bg-background p-2 text-sm"
          value={draft}
          disabled={pending}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="I care more about leafy surroundings than walkability. What would change?"
        />
        <div className="flex gap-2">
          <Button
            type="submit"
            size="sm"
            disabled={pending || !draft.trim() || !availability.data?.configured}
          >
            {pending ? "Working…" : "Discuss"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => {
              setTurns([]);
              setAnalysis(null);
              setComparison(["", ""]);
              setGoals([]);
              setRentalUse("unspecified");
              setError("");
              setUndo(null);
              setDraft("");
              setHousingEnabled(false);
              setHousing({ purchasePrice: "", additionalMonthlyCosts: "" });
              setScenarioEnabled(false);
              setScenario({
                monthlyContribution: "",
                upfrontCapital: "",
                years: "",
                annualReturn: "",
              });
            }}
          >
            Clear conversation
          </Button>
        </div>
      </form>
      <p role="status" className="text-xs">
        {pending ? "Working with the available data and tools…" : error}
      </p>
    </section>
  );
}
