import { describe, expect, it } from "vitest";
import { buildClusterCentroids } from "@/lib/constellation-layout";

describe("buildClusterCentroids", () => {
  it("keeps the fusion cluster at the origin while surrounding dimensions occupy the ring", () => {
    const centroids = buildClusterCentroids([
      ["communication", 18],
      ["learning", 8],
      ["reasoning", 25],
      ["collaboration", 45],
      ["delivery", 74],
      ["fusion", 14],
    ], 700, "fusion");

    expect(centroids.get("fusion")).toMatchObject({ cx: 0, cy: 0 });
    for (const key of ["communication", "learning", "reasoning", "collaboration", "delivery"]) {
      expect(Math.hypot(centroids.get(key)!.cx, centroids.get(key)!.cy)).toBeCloseTo(700, 6);
    }
  });
});
