import { createFileRoute } from "@tanstack/react-router";
import { HousingSearch } from "@/components/housing/HousingSearch";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Housing Search — Find Homes by School District" },
      {
        name: "description",
        content:
          "Interactive map-based housing search with school district overlays, price, beds, and baths filters.",
      },
      { property: "og:title", content: "Housing Search" },
      {
        property: "og:description",
        content: "Find homes by price, beds, baths, and school district.",
      },
    ],
  }),
  component: Index,
});

function Index() {
  return <HousingSearch />;
}
