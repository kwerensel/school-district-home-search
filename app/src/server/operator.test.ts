import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ session: vi.fn(), close: vi.fn(), sql: vi.fn() }));
vi.mock("@tanstack/react-start/server", () => ({ getRequestHeaders: () => new Headers() }));
vi.mock("./auth", () => ({
  createGroundtruthAuth: () => ({
    auth: { api: { getSession: mocks.session } },
    close: mocks.close,
  }),
}));
vi.mock("./db", () => ({ sql: mocks.sql }));
import { requireOperator } from "./operator";
beforeEach(() => {
  vi.resetAllMocks();
  delete process.env.GROUNDTRUTH_OPERATOR_ENABLED;
});
it("denies before reading a session when deployment flag is disabled", async () => {
  await expect(requireOperator()).rejects.toThrow("Operator access unavailable");
  expect(mocks.session).not.toHaveBeenCalled();
});
it("denies signed-out and ordinary users and always closes auth", async () => {
  process.env.GROUNDTRUTH_OPERATOR_ENABLED = "true";
  mocks.session.mockResolvedValueOnce(null);
  await expect(requireOperator()).rejects.toThrow("Operator access unavailable");
  mocks.session.mockResolvedValueOnce({ user: { id: "ordinary", role: "admin" } });
  mocks.sql.mockResolvedValue([]);
  await expect(requireOperator()).rejects.toThrow("Operator access unavailable");
  expect(mocks.close).toHaveBeenCalledTimes(2);
});
it("requires the verified session ID to have a server-owned admin role", async () => {
  process.env.GROUNDTRUTH_OPERATOR_ENABLED = "true";
  mocks.session.mockResolvedValue({ user: { id: "verified-admin" } });
  mocks.sql.mockResolvedValue([{ "?column?": 1 }]);
  expect(await requireOperator()).toBe("verified-admin");
  expect(mocks.sql.mock.calls[0][1]).toBe("verified-admin");
  expect(mocks.close).toHaveBeenCalledTimes(1);
});
