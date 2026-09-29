import { describe, expect, it } from "vitest";
import { fitConstellationCamera } from "@/lib/constellation-camera";

describe("fitConstellationCamera", () => {
  it("centers a single off-origin cluster and uses the available canvas", () => {
    const camera = fitConstellationCamera(
      [
        { x: 180, y: -40 },
        { x: 260, y: 20 },
        { x: 220, y: 80 },
      ],
      900,
      680
    );

    expect(camera.panX).toBeCloseTo(-220 * camera.zoom, 6);
    expect(camera.panY).toBeCloseTo(-20 * camera.zoom, 6);
    expect(camera.zoom).toBeGreaterThan(2);
  });

  it("fits a multi-cluster bounding box without clipping either edge", () => {
    const camera = fitConstellationCamera(
      [
        { x: -300, y: -120 },
        { x: 300, y: 120 },
      ],
      900,
      680
    );

    const left = 900 / 2 + camera.panX - 300 * camera.zoom;
    const right = 900 / 2 + camera.panX + 300 * camera.zoom;
    const top = 680 / 2 + camera.panY - 120 * camera.zoom;
    const bottom = 680 / 2 + camera.panY + 120 * camera.zoom;

    expect(left).toBeGreaterThanOrEqual(camera.padding - 0.01);
    expect(right).toBeLessThanOrEqual(900 - camera.padding + 0.01);
    expect(top).toBeGreaterThanOrEqual(camera.padding - 0.01);
    expect(bottom).toBeLessThanOrEqual(680 - camera.padding + 0.01);
  });
});
