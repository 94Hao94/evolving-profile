export type ClusterCentroid = { cx: number; cy: number };

/** Place an optional integration cluster in the middle and distribute peers around it. */
export function buildClusterCentroids(
  clusters: Array<[key: string, memberCount: number]>,
  ringRadius: number,
  centerKey?: string
): Map<string, ClusterCentroid> {
  const result = new Map<string, ClusterCentroid>();
  const centered = centerKey && clusters.some(([key]) => key === centerKey) ? centerKey : undefined;
  if (centered) result.set(centered, { cx: 0, cy: 0 });

  const ring = clusters.filter(([key]) => key !== centered);
  ring.forEach(([key], index) => {
    const angle = (index / Math.max(ring.length, 1)) * Math.PI * 2 - Math.PI / 2;
    result.set(key, { cx: Math.cos(angle) * ringRadius, cy: Math.sin(angle) * ringRadius });
  });
  return result;
}
