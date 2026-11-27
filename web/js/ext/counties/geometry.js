export const visible = ([x0, y0, x1, y1], vp) =>
  x1 >= vp.x0 && x0 <= vp.x1 && y1 >= vp.y0 && y0 <= vp.y1;

export function bucketRows(rows, bounds, step) {
  const tiles = new Map();
  const range = (lo, hi) => [Math.floor(lo / step), Math.floor(hi / step)];
  function visit([x0, y0, x1, y1], fn) {
    const [a, b] = range(x0, x1);
    const [c, d] = range(y0, y1);
    for (let i = a; i <= b; i++) {
      for (let j = c; j <= d; j++) fn(`${i}/${j}`);
    }
  }
  for (const row of rows) {
    visit(bounds(row), (key) => {
      if (!tiles.has(key)) tiles.set(key, []);
      tiles.get(key).push(row);
    });
  }
  return (vp) => {
    const rows = new Set();
    visit([vp.x0, vp.y0, vp.x1, vp.y1], (key) => {
      for (const row of tiles.get(key) || []) if (visible(bounds(row), vp)) rows.add(row);
    });
    return rows;
  };
}

export function countyPath(row) {
  const path = new Path2D();
  for (const ring of row.rings) {
    path.moveTo(...ring[0]);
    for (let i = 1; i < ring.length; i++) path.lineTo(...ring[i]);
    path.closePath();
  }
  return path;
}
