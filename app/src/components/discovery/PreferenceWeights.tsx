import type { WeightKey } from "@/lib/discovery/profile";

const controls: Array<{ key: WeightKey; label: string }> = [
  { key: "affordability", label: "Local price reach" },
  { key: "green", label: "Tree cover" },
  { key: "walkability", label: "EPA walkability" },
  { key: "lowerRisk", label: "Lower risk" },
  { key: "lowerFlood", label: "Lower flood" },
  { key: "darkSkies", label: "Darker skies" },
  { key: "parkAccess", label: "Park access" },
];

export type PreferenceWeightsProps = {
  weights: Record<WeightKey, number>;
  onWeightChange: (key: WeightKey, value: number) => void;
};

export function PreferenceWeights({
  weights,
  onWeightChange,
  expanded = false,
}: PreferenceWeightsProps & { expanded?: boolean }) {
  const prefix = expanded ? "comparison-weight" : "weight";
  return (
    <fieldset className="min-w-0 space-y-3">
      <legend className="text-sm font-semibold">
        {expanded ? "Adjust your preferences" : "Priorities"}
      </legend>
      {expanded && (
        <p className="text-xs text-muted-foreground">
          0 turns a priority off; 10 gives it the most weight. Changes update your search
          immediately.
        </p>
      )}
      <div className={expanded ? "grid grid-cols-2 gap-x-5 gap-y-2 sm:grid-cols-4" : "space-y-4"}>
        {controls.map(({ key, label }) => (
          <div key={key} className="min-w-0 space-y-1">
            <div className="flex items-center justify-between gap-2 text-xs">
              <label htmlFor={`${prefix}-${key}`}>{label}</label>
              <output htmlFor={`${prefix}-${key}`} className="font-semibold tabular-nums">
                {weights[key]}
              </output>
            </div>
            <input
              id={`${prefix}-${key}`}
              type="range"
              min={0}
              max={10}
              step={1}
              value={weights[key]}
              aria-valuetext={`${weights[key]} out of 10${weights[key] === 0 ? "; off" : ""}`}
              className="h-5 w-full cursor-pointer accent-primary focus-visible:outline-2 focus-visible:outline-ring"
              onChange={(event) => onWeightChange(key, Number(event.target.value))}
            />
          </div>
        ))}
      </div>
    </fieldset>
  );
}
