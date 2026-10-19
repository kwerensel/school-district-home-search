import { describe, expect, it, vi } from "vitest";
import { CommuteQuerySchema, routeDistrictCommutes, withinCommuteCaps } from "./commute";
const anchors = [
  { label: "Office", lat: 40, lng: -75, maxMinutes: 30, mode: "driving-car" as const },
];
describe("request-time commute", () => {
  it("bounds anchors and rejects invalid coordinates", () => {
    expect(
      CommuteQuerySchema.safeParse({ anchors: [...anchors, ...anchors, ...anchors] }).success,
    ).toBe(false);
    expect(CommuteQuerySchema.safeParse({ anchors: [{ ...anchors[0], lat: 91 }] }).success).toBe(
      false,
    );
  });
  it("keeps unreachable cells unknown and fails the cap", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ durations: [[null], [1800]] })));
    const result = await routeDistrictCommutes(
      [
        { districtRegionId: 1, lat: 40, lng: -75 },
        { districtRegionId: 2, lat: 41, lng: -74 },
      ],
      anchors,
      { apiKey: "test", fetcher },
    );
    expect(result.districts[0].anchors[0].minutes).toBeNull();
    expect(withinCommuteCaps(result.districts[0], anchors)).toBe(false);
    expect(withinCommuteCaps(result.districts[1], anchors)).toBe(true);
    expect(result.provenance.origin).toBe("district representative point");
  });
  it("batches sources and explicitly restricts destinations", async () => {
    const fetcher = vi.fn().mockImplementation(async (_url, init) => {
      const body = JSON.parse(init.body);
      return new Response(
        JSON.stringify({ durations: body.sources.map(() => body.destinations.map(() => 60)) }),
      );
    });
    const result = await routeDistrictCommutes(
      Array.from({ length: 100 }, (_, id) => ({ districtRegionId: id + 1, lat: 40, lng: -75 })),
      [...anchors, { ...anchors[0], label: "Second" }],
      { apiKey: "test", fetcher },
    );
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(result.districts).toHaveLength(100);
    const body = JSON.parse(fetcher.mock.calls[0][1].body);
    expect(body.sources).toHaveLength(49);
    expect(body.destinations).toEqual([49, 50]);
  });
  it("classifies provider rejection without exposing provider body or coordinates", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response("provider detail that must remain private", { status: 429 }));
    await expect(
      routeDistrictCommutes([{ districtRegionId: 1, lat: 40, lng: -75 }], anchors, {
        apiKey: "test",
        fetcher,
      }),
    ).rejects.toMatchObject({
      name: "CommuteRoutingError",
      status: 429,
      message: "Commute routing is unavailable. Try again later.",
    });
  });
  it("rejects partial matrices rather than treating missing routes as zero", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ durations: [] })));
    await expect(
      routeDistrictCommutes([{ districtRegionId: 1, lat: 40, lng: -75 }], anchors, {
        apiKey: "test",
        fetcher,
      }),
    ).rejects.toThrow("incomplete");
  });
});
