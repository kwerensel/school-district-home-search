import { createFileRoute } from "@tanstack/react-router";
import { HousingSearch } from "@/components/housing/HousingSearch";

export const Route = createFileRoute("/explore")({
  head: () => ({
    meta: [
      { title: "Groundtruth Explorer — Find Homes by Verified School District" },
      {
        name: "description",
        content:
          "Browse frozen listings assigned to official school-district polygons with environmental context.",
      },
    ],
  }),
  component: Explore,
});

function Explore() {
  return <HousingSearch />;
}
