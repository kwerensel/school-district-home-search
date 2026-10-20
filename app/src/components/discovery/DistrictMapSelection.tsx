import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function DistrictMapSelection({
  districts,
  selectedSlugs,
  onChange,
}: {
  districts: Array<{ districtSlug: string; districtName: string }>;
  selectedSlugs: string[];
  onChange: (slugs: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = districts.filter((district) =>
    district.districtName.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <section className="space-y-2 rounded-md border p-3" aria-label="District map selection">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Districts to show on the map</h2>
        {selectedSlugs.length > 0 && (
          <Button type="button" size="sm" variant="ghost" onClick={() => onChange([])}>
            Show all
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {selectedSlugs.length
          ? `${selectedSlugs.length} selected`
          : `All ${districts.length} districts`}
        . Select any number of districts, then choose the map's color layer independently. Match
        ranking still uses the full region scope.
      </p>
      <Input
        aria-label="Find districts for the map"
        placeholder="Find districts…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="max-h-36 space-y-1 overflow-y-auto" aria-label="District selection options">
        {visible.map((district) => (
          <label
            key={district.districtSlug}
            className="flex cursor-pointer items-center gap-2 text-sm"
          >
            <input
              type="checkbox"
              checked={selectedSlugs.includes(district.districtSlug)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...selectedSlugs, district.districtSlug]
                    : selectedSlugs.filter((slug) => slug !== district.districtSlug),
                )
              }
            />
            {district.districtName}
          </label>
        ))}
      </div>
    </section>
  );
}
