import { describe, expect, it } from "vitest";
import { localToday } from "../components/DashboardPage.jsx";

describe("DashboardPage helpers", () => {
  it("localToday returns the local date in YYYY-MM-DD", () => {
    const d = new Date();
    const expected = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    expect(localToday()).toBe(expected);
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
