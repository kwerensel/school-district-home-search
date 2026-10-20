import { useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { searchDiscoveryPlaces } from "@/lib/discovery/conversation.functions";
import type { Place } from "@/lib/discovery/places";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function PlaceComparison({
  regionGroup,
  selected,
  onChange,
  pending,
  onCompare,
}: {
  regionGroup: "all" | "pa-mainline" | "hudson-valley";
  selected: Place[];
  onChange: (places: Place[]) => void;
  pending: boolean;
  onCompare: () => void;
}) {
  const search = useServerFn(searchDiscoveryPlaces);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const scope = useRef(regionGroup);
  scope.current = regionGroup;
  async function find() {
    if (busy || query.trim().length < 2) return;
    const originalScope = regionGroup;
    setBusy(true);
    setMessage("");
    try {
      const reply = await search({ data: { query: query.trim(), regionGroup } });
      if (scope.current !== originalScope) {
        setResults([]);
        setMessage("Region changed. Search again in the current region.");
        return;
      }
      if (reply.status === "ok") {
        setResults(reply.places);
        if (!reply.places.length)
          setMessage(
            "No verified place matches. Informal neighborhood names may not be in the catalog; try a town or known area. No outside search was performed.",
          );
      } else setMessage(reply.message);
    } catch {
      setMessage("Place search could not connect. Please try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="space-y-2 text-xs">
      <summary className="cursor-pointer font-medium">
        Compare places with verified data (optional)
      </summary>
      <p className="mt-2 text-muted-foreground">
        Search towns, municipalities, census tracts or districts. Coverage and geographic scale are
        shown with each result. District selection is optional.
      </p>
      <form
        className="my-2 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void find();
        }}
      >
        <Input
          aria-label="Find a place"
          placeholder="Town, area or census tract name"
          maxLength={120}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="submit" size="sm" disabled={busy || pending || query.trim().length < 2}>
          {busy ? "Searching…" : "Find"}
        </Button>
      </form>
      <div className="space-y-1">
        {results.map((place) => (
          <div
            key={place.slug}
            className="flex items-center justify-between gap-2 rounded border p-2"
          >
            <span>
              {place.name} · {place.kind.replaceAll("_", " ")}
            </span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                pending || selected.length >= 2 || selected.some((item) => item.slug === place.slug)
              }
              onClick={() => onChange([...selected, place])}
            >
              Add
            </Button>
          </div>
        ))}
      </div>
      {selected.map((place) => (
        <p key={place.slug} className="my-2 flex items-center justify-between gap-2">
          {place.name} · {place.kind.replaceAll("_", " ")}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={pending}
            onClick={() => onChange(selected.filter((item) => item.slug !== place.slug))}
          >
            Remove
          </Button>
        </p>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={pending || !selected.length}
        onClick={onCompare}
      >
        Compare selected places
      </Button>
      <p role="status" className="mt-2 text-muted-foreground">
        {message}
      </p>
    </details>
  );
}
