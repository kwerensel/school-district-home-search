import { createFileRoute } from "@tanstack/react-router";
import { DiscoveryEngine } from "@/components/discovery/DiscoveryEngine";

export const Route = createFileRoute("/discover/results")({
  head: () => ({
    meta: [
      { title: "Groundtruth Discovery Results" },
      {
        name: "description",
        content: "Rank and compare supported school districts by budget and lifestyle priorities.",
      },
    ],
  }),
  component: DiscoveryResults,
});

function DiscoveryResults() {
  return <DiscoveryEngine />;
}
