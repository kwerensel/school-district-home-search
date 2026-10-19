import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { getDistrictComparison } from "@/lib/discovery/comparison.functions";
import type { PurchasingPowerQuery } from "@/lib/finance/server-data";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  districtIds: number[];
  profile: PurchasingPowerQuery;
};

export function DistrictComparisonDrawer({ open, onOpenChange, districtIds, profile }: Props) {
  const compare = useServerFn(getDistrictComparison);
  const [regionAId, regionBId] = districtIds;
  const query = useQuery({
    queryKey: ["district-comparison", regionAId, regionBId, profile],
    queryFn: () => compare({ data: { regionAId, regionBId, profile } }),
    enabled: open && districtIds.length === 2,
    staleTime: 60 * 1000,
    retry: false,
  });
  const result = query.data;
  const payload = result?.payload;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="z-[1200] w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Compare districts</SheetTitle>
          <SheetDescription>
            District estimates use your current budget and priorities. Differences below subtract
            the second district from the first.
          </SheetDescription>
        </SheetHeader>
        {query.isPending ? (
          <p className="mt-6 text-sm text-muted-foreground" role="status">
            Loading comparison…
          </p>
        ) : query.isError ? (
          <div className="mt-6 space-y-3" role="alert">
            <p className="text-sm">
              The comparison could not be loaded. Your selected districts are still available.
            </p>
            <Button onClick={() => void query.refetch()}>Try again</Button>
          </div>
        ) : payload ? (
          <div className="mt-6 space-y-6">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">First district</p>
                <p className="mt-1 font-semibold">{payload.regionA.name}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Second district</p>
                <p className="mt-1 font-semibold">{payload.regionB.name}</p>
              </div>
            </div>
            <section className="rounded-md border border-border p-4">
              <h3 className="text-sm font-semibold">First minus second</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Positive means the first district has a higher value. A higher value is not always
                preferable.
              </p>
              <dl className="mt-4 space-y-3 text-sm">
                <Difference
                  label="Estimated max home price"
                  value={payload.maxPurchasePriceDelta}
                />
                <Difference
                  label="District median home value"
                  value={payload.medianHomeValueDelta}
                />
                <Difference
                  label="Drive time to the same city anchor"
                  value={payload.commuteMinutesDelta}
                />
              </dl>
              {payload.commuteMinutesDelta === null ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  Drive times are compared only when both districts share the same regional
                  destination and have available data.
                </p>
              ) : null}
            </section>
            {payload.topMetricGaps.length ? (
              <section>
                <h3 className="mb-3 text-sm font-semibold">District context</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="pb-2 pr-3" scope="col">
                          Metric
                        </th>
                        <th className="pb-2 pr-3" scope="col">
                          First
                        </th>
                        <th className="pb-2" scope="col">
                          Second
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {payload.topMetricGaps.map((gap) => (
                        <tr key={gap.label} className="border-b border-border">
                          <th className="py-3 pr-3 font-medium" scope="row">
                            {gap.label}
                          </th>
                          <td className="py-3 pr-3">{gap.regionAValue}</td>
                          <td className="py-3">{gap.regionBValue}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}
            <section className="rounded-md bg-muted p-4">
              <h3 className="text-sm font-semibold">Tradeoffs</h3>
              <p className="mt-2 text-sm leading-6">{result.narrative}</p>
              <p className="mt-3 text-xs text-muted-foreground">
                {result.source === "claude"
                  ? "AI explanation checked against the comparison values."
                  : "Explanation generated from the comparison values."}
              </p>
            </section>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Difference({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-wrap justify-between gap-2">
      <dt>{label}</dt>
      <dd className="font-medium">{value ?? "Not available"}</dd>
    </div>
  );
}
