import type { Evidence } from "@/lib/discovery/conversation";

const metricLabels: Record<string, string> = {
  effective_tax_rate: "Effective property-tax rate",
  median_home_value: "Median home value",
  tree_canopy_pct: "Tree canopy",
  walkability_index: "EPA walkability",
  park_access: "Park access",
};
const sourceNumber = new Intl.NumberFormat("en-US", { maximumSignificantDigits: 5 });

export function DiscoveryEvidence({ evidence }: { evidence: Evidence[] }) {
  return (
    <div className="space-y-2">
      {evidence.map((card) => (
        <details key={card.id} className="rounded border p-2 text-xs">
          <summary className="cursor-pointer font-medium">
            {card.kind === "verified-data"
              ? "Verified data + code estimates"
              : card.kind === "calculation"
                ? "Calculation / assumptions"
                : "Unknown / needs research"}
            : {card.title}
          </summary>
          <p className="mt-2 whitespace-pre-wrap">{card.details}</p>
          {card.provenance?.length ? (
            <ul className="mt-2 space-y-1 border-t pt-2" aria-label="Metric sources">
              {card.provenance.map((source, index) => (
                <li key={`${source.metricKey}-${source.vintage}-${index}`}>
                  {source.regionName ? `${source.regionName} — ` : ""}
                  {metricLabels[source.metricKey] ?? source.metricKey}:{" "}
                  {source.value === null ? "unavailable" : sourceNumber.format(source.value)}{" "}
                  {source.units ?? "(units unavailable)"} — {source.source ?? "source unavailable"};
                  vintage {source.vintage}; native resolution{" "}
                  {source.nativeResolution ?? "unavailable"}. Geographic context as labeled above.
                </li>
              ))}
            </ul>
          ) : null}
        </details>
      ))}
    </div>
  );
}
