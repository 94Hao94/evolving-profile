export type ConstellationPoint = { x: number; y: number };

export type ConstellationCamera = {
  panX: number;
  panY: number;
  zoom: number;
  padding: number;
};

/**
 * Fit the actual node bounds, rather than their distance from the world origin.
 * This keeps a single clustered view centered even when its layout centroid is
 * deliberately offset from (0, 0).
 */
export function fitConstellationCamera(
  points: ConstellationPoint[],
  width: number,
  height: number,
  padding = 72
): ConstellationCamera {
  if (!points.length || width <= 0 || height <= 0) {
    return { panX: 0, panY: 0, zoom: 0.5, padding };
  }

  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const spanX = Math.max(maxX - minX, 80);
  const spanY = Math.max(maxY - minY, 80);
  const availableWidth = Math.max(width - padding * 2, 1);
  const availableHeight = Math.max(height - padding * 2, 1);
  const zoom = Math.max(0.1, Math.min(4, availableWidth / spanX, availableHeight / spanY));
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  return {
    panX: -centerX * zoom,
    panY: -centerY * zoom,
    zoom,
    padding,
  };
}
