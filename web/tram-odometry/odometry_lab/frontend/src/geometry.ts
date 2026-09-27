// Centripetal Catmull–Rom, per contiguous route; no change to numeric predictions.
export function smoothRoute(input: [number, number][]): [number, number][] {
  if (input.length < 3) return input;
  const points = input.filter(
    (p, i) =>
      i === 0 ||
      Math.hypot(p[0] - input[i - 1][0], p[1] - input[i - 1][1]) > 1e-10,
  );
  if (points.length < 3) return points;
  const result: [number, number][] = [];
  const mix = (a: number[], b: number[], ta: number, tb: number, t: number) =>
    a.map((v, j) => ((tb - t) * v + (t - ta) * b[j]) / (tb - ta));
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i],
      p2 = points[i + 1],
      p0 = i ? points[i - 1] : p1.map((v, j) => 2 * v - p2[j]),
      p3 =
        i + 2 < points.length ? points[i + 2] : p2.map((v, j) => 2 * v - p1[j]);
    const metric = (a: number[], b: number[]) =>
      Math.sqrt(
        Math.max(
          1e-12,
          Math.hypot(
            a[0] - b[0],
            (a[1] - b[1]) * Math.cos(((a[0] + b[0]) * Math.PI) / 360),
          ),
        ),
      );
    const t0 = 0,
      t1 = metric(p0, p1),
      t2 = t1 + metric(p1, p2),
      t3 = t2 + metric(p2, p3);
    for (let j = 0; j < 4; j++) {
      const t = t1 + ((t2 - t1) * j) / 4;
      const a = mix(p0, p1, t0, t1, t),
        b = mix(p1, p2, t1, t2, t),
        c = mix(p2, p3, t2, t3, t);
      const d = mix(a, b, t0, t2, t),
        e = mix(b, c, t1, t3, t);
      result.push(mix(d, e, t1, t2, t) as [number, number]);
    }
  }
  result.push(points[points.length - 1]);
  return result;
}
