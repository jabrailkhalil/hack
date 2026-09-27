import { describe, it, expect } from "vitest";
import { smoothRoute } from "./geometry";
import { nearest } from "./types";
describe("display geometry", () => {
  it("preserves endpoints, chronology and finite values around duplicated stops", () => {
    const points: [number, number][] = [
      [55, 37],
      [55, 37],
      [55.001, 37],
      [55.001, 37.001],
      [55, 37],
    ];
    const result = smoothRoute(points);
    expect(result[0]).toEqual(points[0]);
    expect(result.at(-1)).toEqual(points.at(-1));
    expect(result.flat().every(Number.isFinite)).toBe(true);
    expect(result.length).toBeGreaterThan(points.length);
  });
  it("does not mutate numeric route data", () => {
    const p: [number, number][] = [
      [1, 1],
      [2, 2],
      [3, 1],
    ];
    const original = JSON.stringify(p);
    smoothRoute(p);
    expect(JSON.stringify(p)).toBe(original);
  });
  it("locates replay timestamps at the endpoints and between samples", () => {
    expect(nearest([0, 1, 2], 0.9)).toBe(1);
    expect(nearest([0, 1, 2], -1)).toBe(0);
    expect(nearest([0, 1, 2], 4)).toBe(2);
  });
});
