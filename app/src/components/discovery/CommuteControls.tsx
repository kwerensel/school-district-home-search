import { useMutation } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { geocodeCommuteAddress } from "@/lib/discovery/geocode.functions";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CommuteAnchorSchema, type CommuteAnchor } from "@/lib/discovery/profile";

export function CommuteControls({
  anchors,
  onChange,
}: {
  anchors: CommuteAnchor[];
  onChange: (anchors: CommuteAnchor[]) => void;
}) {
  const geocode = useServerFn(geocodeCommuteAddress);
  const [address, setAddress] = useState("");
  const lookup = useMutation({
    mutationFn: (value: string) => geocode({ data: { address: value } }),
  });
  const [label, setLabel] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [cap, setCap] = useState("45");
  const [error, setError] = useState("");
  function add() {
    const parsed = CommuteAnchorSchema.safeParse({
      label,
      lat: lat.trim() ? Number(lat) : NaN,
      lng: lng.trim() ? Number(lng) : NaN,
      maxMinutes: Number(cap),
      mode: "driving-car",
    });
    if (!parsed.success || anchors.length >= 2) {
      setError(
        "Enter a name, valid latitude and longitude, and a drive-time cap between 1 and 240 minutes.",
      );
      return;
    }
    onChange([...anchors, parsed.data]);
    setLabel("");
    setLat("");
    setLng("");
    setError("");
  }
  return (
    <section className="space-y-3 rounded-md border border-border p-4">
      <h3 className="text-sm font-semibold">Commute destinations (optional)</h3>
      <p className="text-xs text-muted-foreground">
        Add up to two destinations by address or coordinates. Districts must meet every drive-time
        cap. Routes start at a representative point inside each district, not at a listing or a
        population-weighted origin. Estimates exclude live traffic.
      </p>
      <p className="text-xs text-muted-foreground">
        Destinations are included in this shareable URL and in a saved profile. Use a nearby public
        location if you prefer.
      </p>
      <ol className="space-y-2">
        {anchors.map((anchor, index) => (
          <li key={index} className="rounded border border-border p-2 text-xs">
            <p className="font-medium">{anchor.label}</p>
            <p>
              {anchor.lat}, {anchor.lng} · up to {anchor.maxMinutes} min driving
            </p>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChange(anchors.filter((_, i) => i !== index))}
              aria-label={`Remove ${anchor.label} commute destination`}
            >
              Remove
            </Button>
          </li>
        ))}
      </ol>
      {anchors.length < 2 ? (
        <div className="space-y-3">
          <div className="space-y-2 rounded-md bg-muted p-3">
            <Label htmlFor="commute-address">Find destination address (optional)</Label>
            <Input
              id="commute-address"
              value={address}
              maxLength={240}
              onChange={(event) => {
                setAddress(event.target.value);
                lookup.reset();
              }}
              placeholder="Street address, city, state"
            />
            <p className="text-xs text-muted-foreground">
              Search sends this address to Geocodio. Confirm a candidate before adding it to your
              commute destinations.
            </p>
            <Button
              size="sm"
              variant="outline"
              disabled={address.trim().length < 8 || lookup.isPending}
              onClick={() => lookup.mutate(address.trim())}
            >
              {lookup.isPending ? "Looking up address…" : "Look up address"}
            </Button>
            {lookup.isError ? (
              <p className="text-xs text-muted-foreground" role="alert">
                Address lookup is unavailable or its free allowance is used. Enter coordinates below
                or try later.
              </p>
            ) : null}
            {lookup.isSuccess && !lookup.data.candidates.length ? (
              <p className="text-xs text-muted-foreground">
                No matching address found. Try a more complete address or enter coordinates.
              </p>
            ) : null}
            {lookup.data?.candidates.map((candidate, index) => (
              <div
                className="space-y-1 border-t border-border pt-2 text-xs"
                key={`${candidate.lat}-${candidate.lng}-${index}`}
              >
                <p>{candidate.label}</p>
                <p>
                  {candidate.lat}, {candidate.lng} · confidence{" "}
                  {(candidate.accuracy * 100).toFixed(0)}%
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setLabel(candidate.label);
                    setLat(String(candidate.lat));
                    setLng(String(candidate.lng));
                    lookup.reset();
                  }}
                >
                  Use this destination
                </Button>
              </div>
            ))}
          </div>
          <div className="space-y-1">
            <Label htmlFor="commute-name">Destination name</Label>
            <Input
              id="commute-name"
              value={label}
              maxLength={160}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Office or public landmark"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label htmlFor="commute-lat">Latitude</Label>
              <Input
                id="commute-lat"
                inputMode="decimal"
                value={lat}
                onChange={(event) => setLat(event.target.value)}
                placeholder="40.0"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="commute-lng">Longitude</Label>
              <Input
                id="commute-lng"
                inputMode="decimal"
                value={lng}
                onChange={(event) => setLng(event.target.value)}
                placeholder="-75.0"
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="commute-cap">Maximum drive minutes</Label>
            <Input
              id="commute-cap"
              type="number"
              min={1}
              max={240}
              value={cap}
              onChange={(event) => setCap(event.target.value)}
            />
          </div>
          {error ? (
            <p className="text-xs text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button size="sm" variant="outline" onClick={add}>
            Add destination
          </Button>
        </div>
      ) : null}
    </section>
  );
}
