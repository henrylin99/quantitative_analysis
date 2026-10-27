/**
 * Squarified treemap (Bruls, Huijing, van Wijk 2000).
 *
 * Given items `{ value }` and a container rectangle, returns an array of
 * laid-out rectangles `{ ...item, x, y, width, height }` whose areas are
 * proportional to `value` and whose aspect ratios are kept close to 1.
 *
 * This is what TradingView's market heatmap uses to size tiles by market cap.
 */

function worst(row, shortSide) {
  const sum = row.reduce((s, i) => s + i.area, 0);
  if (sum === 0) return Infinity;
  const areas = row.map((i) => i.area);
  const rmax = Math.max(...areas);
  const rmin = Math.min(...areas);
  const s2 = sum * sum;
  const w2 = shortSide * shortSide;
  return Math.max((w2 * rmax) / s2, s2 / (w2 * rmin));
}

// Lay out one "row" along the short side of `rect`; return the remaining rect.
function layoutRow(row, rect, out) {
  const { x, y, width, height } = rect;
  const sum = row.reduce((s, i) => s + i.area, 0);
  if (width >= height) {
    // short side = height → stack a column on the left
    const colW = sum / height;
    let oy = y;
    for (const item of row) {
      const h = item.area / colW;
      out.push({ ...item, x, y: oy, width: colW, height: h });
      oy += h;
    }
    return { x: x + colW, y, width: width - colW, height };
  }
  // short side = width → stack a row on top
  const rowH = sum / width;
  let ox = x;
  for (const item of row) {
    const w = item.area / rowH;
    out.push({ ...item, x: ox, y, width: w, height: rowH });
    ox += w;
  }
  return { x, y: y + rowH, width, height: height - rowH };
}

function squarify(items, row, shortSide, rect, out) {
  if (items.length === 0) {
    if (row.length) layoutRow(row, rect, out);
    return;
  }
  const next = items[0];
  const newRow = [...row, next];
  if (row.length === 0 || worst(newRow, shortSide) <= worst(row, shortSide)) {
    squarify(items.slice(1), newRow, shortSide, rect, out);
  } else {
    const rest = layoutRow(row, rect, out);
    squarify(items, [], Math.min(rest.width, rest.height), rest, out);
  }
}

export function treemap(items, x, y, width, height) {
  const valid = items
    .filter((i) => i && i.value > 0)
    .map((i) => ({ ...i }))
    .sort((a, b) => b.value - a.value);
  if (!valid.length || width <= 0 || height <= 0) return [];
  const total = valid.reduce((s, i) => s + i.value, 0);
  const scale = (width * height) / total;
  valid.forEach((i) => (i.area = i.value * scale));
  const out = [];
  squarify(valid, [], Math.min(width, height), { x, y, width, height }, out);
  return out;
}
