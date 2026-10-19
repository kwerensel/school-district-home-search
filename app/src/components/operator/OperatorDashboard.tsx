import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createOperatorDraft, getOperatorOverview } from "@/lib/operator/operator.functions";

export function OperatorDashboard() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["operator-overview"],
    queryFn: () => getOperatorOverview(),
    retry: false,
  });
  const [region, setRegion] = useState<"pa-mainline" | "hudson-valley">("pa-mainline");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [counties, setCounties] = useState("");
  const draft = useMutation({
    mutationFn: createOperatorDraft,
    onSuccess: () => client.invalidateQueries({ queryKey: ["operator-overview"] }),
  });
  if (query.isPending) return <main className="p-8">Checking operator access…</main>;
  if (query.isError)
    return (
      <main className="p-8">
        <h1 className="text-xl font-semibold">Operator access unavailable</h1>
        <a href="/discover">Return to Discovery</a>
      </main>
    );
  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Groundtruth operator</h1>
        <p className="text-sm text-muted-foreground">
          Private workflows · frozen baseline: 4,505 listings · provider calls and outreach disabled
        </p>
      </header>
      <section className="space-y-3 rounded-lg border p-4">
        <h2 className="font-semibold">Listing refresh dry run</h2>
        <p className="text-sm">
          Create a review job. Counts and credits remain unknown until an approved provider supplies
          an estimate. No listings are fetched or changed.
        </p>
        <label className="block">
          Area{" "}
          <select
            value={region}
            onChange={(event) => setRegion(event.target.value as typeof region)}
            className="ml-2 rounded border p-2"
          >
            <option value="pa-mainline">PA Main Line</option>
            <option value="hudson-valley">Hudson Valley</option>
          </select>
        </label>
        <button
          className="rounded border px-3 py-2"
          disabled={draft.isPending}
          onClick={() => draft.mutate({ data: { kind: "listing_refresh", region } })}
        >
          Create dry-run draft
        </button>
      </section>
      <form
        className="space-y-3 rounded-lg border p-4"
        onSubmit={(event) => {
          event.preventDefault();
          draft.mutate({
            data: {
              kind: "region_expansion",
              slug,
              name,
              counties: counties
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            },
          });
        }}
      >
        <h2 className="font-semibold">Region manifest draft</h2>
        <p className="text-sm">
          Official county FIPS codes are reviewed before scaffolding, coverage checks, validation,
          QA and explicit promotion.
        </p>
        <label className="block">
          Region slug
          <input
            required
            pattern="[a-z0-9][a-z0-9-]*"
            className="ml-2 rounded border p-2"
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
          />
        </label>
        <label className="block">
          Name
          <input
            required
            className="ml-2 rounded border p-2"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="block">
          County FIPS codes, comma-separated
          <input
            required
            className="ml-2 rounded border p-2"
            placeholder="42029, 42045"
            value={counties}
            onChange={(event) => setCounties(event.target.value)}
          />
        </label>
        <button className="rounded border px-3 py-2" disabled={draft.isPending}>
          Create manifest draft
        </button>
      </form>
      {draft.isError && (
        <p role="alert">Could not create the draft. Check the inputs and try again.</p>
      )}
      {draft.isSuccess && (
        <pre className="overflow-auto rounded bg-muted p-3 text-xs">
          {JSON.stringify(draft.data, null, 2)}
        </pre>
      )}
      <section>
        <h2 className="font-semibold">Recent jobs</h2>
        {query.data.jobs.length ? (
          <ul>
            {query.data.jobs.map((job) => (
              <li key={String(job.id)} className="border-b py-2">
                #{String(job.id)} · {String(job.kind)} · {String(job.target)} · {String(job.phase)}
              </li>
            ))}
          </ul>
        ) : (
          <p>No jobs yet.</p>
        )}
      </section>
      <section>
        <h2 className="font-semibold">Attendance evidence and outreach</h2>
        <p className="text-sm">
          School year and grade band are required. Only reviewed official polygons or scoped written
          confirmations can establish a school assignment. Outreach remains a draft queue.
        </p>
        <p className="text-sm">{query.data.outreach.length} queued records.</p>
      </section>
      <a href="/discover">Back to Discovery</a>
    </main>
  );
}
