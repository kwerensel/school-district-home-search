import { expect, it, vi } from "vitest";
import { geocodeAddress, GeocodeQuerySchema } from "./geocode";
it("bounds input and sends one address with no paid appends or key in URL", async () => {
  expect(GeocodeQuerySchema.safeParse({ address: "x" }).success).toBe(false);
  const fetcher = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        results: [
          {
            formatted_address: "100 Main St, Example, PA",
            location: { lat: 40, lng: -75 },
            accuracy: 1,
            source: "County GIS",
          },
          { formatted_address: "Bad", location: { lat: 1000, lng: 0 }, accuracy: 1 },
        ],
      }),
    ),
  );
  const result = await geocodeAddress("100 Main St, Example, PA", {
    apiKey: "secret-test",
    fetcher,
  });
  expect(result.candidates).toHaveLength(1);
  expect(result.candidates[0].source).toBe("County GIS");
  const url = fetcher.mock.calls[0][0] as URL;
  expect(url.searchParams.has("fields")).toBe(false);
  expect(url.href).not.toContain("secret-test");
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer secret-test");
});
it("returns sanitized provider failures", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response("secret upstream error", { status: 403 }));
  await expect(
    geocodeAddress("100 Main St, Example, PA", { apiKey: "test", fetcher }),
  ).rejects.toThrow("Address lookup unavailable");
});
