import { createFileRoute } from "@tanstack/react-router";
import { DiscoveryEngine } from "@/components/discovery/DiscoveryEngine";

export const Route = createFileRoute("/discover")({
  head: () => ({
    meta: [
      { title: "Groundtruth Discovery" },
      {
        name: "description",
        content: "Compare school districts by budget-adjusted purchasing power.",
      },
    ],
  }),
  component: Discovery,
});

function Discovery() {
  return <DiscoveryEngine />;
}
