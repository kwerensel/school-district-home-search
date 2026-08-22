import { useEffect, useState } from "react";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Filters } from "@/lib/housing/types";
import { DEFAULT_FILTERS } from "@/lib/housing/filters";

interface Props {
  filters: Filters;
  setFilters: (f: Filters) => void;
  districts: string[];
  priceMax: number;
  resultCount: number;
  totalCount: number;
}

const formatPrice = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(2)}M` : `$${Math.round(n / 1000)}k`;

export function FiltersSidebar({
  filters,
  setFilters,
  districts,
  priceMax,
  resultCount,
  totalCount,
}: Props) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const update = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters({ ...filters, [key]: value });

  return (
    <div className="flex h-full flex-col gap-6 p-5">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Filters</h2>
        <p className="text-xs text-muted-foreground">
          {resultCount} of {totalCount} listings
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Max price</Label>
          <span className="text-sm font-medium text-foreground">
            {formatPrice(filters.maxPrice)}
          </span>
        </div>
        <Slider
          min={50_000}
          max={Math.max(priceMax, 100_000)}
          step={10_000}
          value={[Math.min(filters.maxPrice, priceMax)]}
          onValueChange={(v) => update("maxPrice", v[0])}
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Min beds</Label>
          <span className="text-sm font-medium text-foreground">{filters.minBeds}+</span>
        </div>
        <div className="flex gap-1">
          {[0, 1, 2, 3, 4, 5].map((n) => (
            <Button
              key={n}
              type="button"
              size="sm"
              variant={filters.minBeds === n ? "default" : "outline"}
              className="flex-1"
              onClick={() => update("minBeds", n)}
            >
              {n === 0 ? "Any" : `${n}+`}
            </Button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Min baths</Label>
          <span className="text-sm font-medium text-foreground">{filters.minBaths}+</span>
        </div>
        <div className="flex gap-1">
          {[0, 1, 2, 3, 4].map((n) => (
            <Button
              key={n}
              type="button"
              size="sm"
              variant={filters.minBaths === n ? "default" : "outline"}
              className="flex-1"
              onClick={() => update("minBaths", n)}
            >
              {n === 0 ? "Any" : `${n}+`}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between rounded-md border border-border p-3">
        <div>
          <Label htmlFor="good-only" className="cursor-pointer">
            Good districts only
          </Label>
          <p className="text-xs text-muted-foreground">Curated prototype placeholder</p>
        </div>
        <Switch
          id="good-only"
          checked={filters.goodOnly}
          onCheckedChange={(v) => update("goodOnly", v)}
        />
      </div>

      <div className="space-y-2">
        <Label>Nearby tree coverage</Label>
        {mounted ? (
          <Select
            value={filters.treeCover}
            onValueChange={(value) => update("treeCover", value as Filters["treeCover"])}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any coverage</SelectItem>
              <SelectItem value="some">Some trees or more</SelectItem>
              <SelectItem value="leafy">Leafy or more</SelectItem>
              <SelectItem value="very-leafy">Very leafy</SelectItem>
            </SelectContent>
          </Select>
        ) : (
          <div className="flex h-9 w-full items-center rounded-md border border-input px-3 text-sm">
            Any coverage
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          Based on the share of land covered by trees within 100 m.
        </p>
      </div>

      <div className="flex items-center justify-between rounded-md border border-border p-3">
        <div>
          <Label htmlFor="flood-only" className="cursor-pointer">
            Inside FEMA high-risk flood zone
          </Label>
          <p className="text-xs text-muted-foreground">
            Property point falls inside the mapped zone
          </p>
        </div>
        <Switch
          id="flood-only"
          checked={filters.floodOnly}
          onCheckedChange={(v) => update("floodOnly", v)}
        />
      </div>

      <div className="space-y-2">
        <Label>School district</Label>
        {mounted ? (
          <Select value={filters.district} onValueChange={(v) => update("district", v)}>
            <SelectTrigger>
              <SelectValue placeholder="All districts" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All districts</SelectItem>
              {districts.map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <div className="flex h-9 w-full items-center rounded-md border border-input bg-transparent px-3 text-sm text-foreground">
            {filters.district === "all" ? "All districts" : filters.district}
          </div>
        )}
      </div>

      <Button
        variant="outline"
        onClick={() => setFilters({ ...DEFAULT_FILTERS, maxPrice: priceMax })}
      >
        Reset filters
      </Button>
    </div>
  );
}
