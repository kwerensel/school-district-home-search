import { describe, expect, it, vi } from "vitest";
import { createSavedStore } from "./store";
import { DEFAULT_DISCOVERY_PROFILE } from "@/lib/discovery/profile";

describe("session-owned saved data", () => {
  it("rejects an absent verified owner", () => {
    expect(() => createSavedStore(vi.fn(), "")).toThrow("AUTH_REQUIRED");
  });

  it("binds every query to the verified session owner and preserves the validated profile", async () => {
    const execute = vi.fn().mockResolvedValue([
      {
        id: 1,
        name: "Search",
        profile: DEFAULT_DISCOVERY_PROFILE,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const store = createSavedStore(execute, "session-owner");
    const profile = {
      ...DEFAULT_DISCOVERY_PROFILE,
      grossMonthlyIncome: 15000,
      monthlyDebt: 500,
      wizardStep: "results" as const,
      shortlist: ["district-a"],
    };
    await store.saveProfile({ name: "Search", profile });
    expect(execute.mock.calls[0][1].slice(0, 2)).toEqual(["session-owner", "Search"]);
    expect(JSON.parse(execute.mock.calls[0][1][2])).toEqual(profile);
    await store.listProfiles();
    expect(execute.mock.calls[1][1]).toEqual(["session-owner"]);
    await store.deleteProfile({ id: 7 });
    expect(execute.mock.calls[2][1]).toEqual([7, "session-owner"]);
    expect(execute.mock.calls[2][0]).toContain("user_id = $2");
  });

  it("reads favorite districts from the unified district table", async () => {
    const execute = vi.fn().mockResolvedValue([]);
    await createSavedStore(execute, "session-owner").listFavorites();
    expect(execute.mock.calls[0][0]).toContain("JOIN school_districts d ON d.id = l.district_id");
    expect(execute.mock.calls[0][0]).toContain("d.name_display AS school_district");
    expect(execute.mock.calls[0][1]).toEqual(["session-owner"]);
  });

  it("removes an existing favorite without reinserting it and adds an absent favorite", async () => {
    const execute = vi
      .fn()
      .mockResolvedValueOnce([{ listing_id: 5 }])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([]);
    const store = createSavedStore(execute, "session-owner");
    expect(await store.toggleFavorite({ listingId: 5 })).toEqual({ favorite: false });
    expect(execute).toHaveBeenCalledTimes(1);
    expect(await store.toggleFavorite({ listingId: 5 })).toEqual({ favorite: true });
    expect(execute).toHaveBeenCalledTimes(3);
    expect(execute.mock.calls.every((call) => call[1][0] === "session-owner")).toBe(true);
  });
});
