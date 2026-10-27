// 美股扫描器六维打分的共享纯函数。六个 scan_* 打分 lib 都从这里取
// 同一套截面排序约定（平均名次法百分位），保证跨维度的分数可比；
// 页面用 median / histogram / bandFor 做分布统计与档位着色。
// 纯函数、无副作用：页面组件与本目录各打分 lib 共享同一实现。

// 截面百分位（0–1，平均名次法，并列值取平均）。只统计有限数值；
// v 非有限或序列为空返回 null。单元素序列约定 0.5。
export function percentileRank(vals, v) {
  const xs = [];
  for (const x of vals) if (Number.isFinite(x)) xs.push(x);
  const n = xs.length;
  if (!n || !Number.isFinite(v)) return null;
  if (n === 1) return 0.5;
  let less = 0;
  let eq = 0;
  for (const x of xs) {
    if (x < v) less++;
    else if (x === v) eq++;
  }
  const rank = less + (eq - 1) / 2; // 0 起的平均名次
  return rank / (n - 1); // → 0..1
}

// 某一列的截面百分位（0–100）。value 为 null/非有限时返回 null。
export function percentileOf(rows, key, value) {
  const p = percentileRank(rows.map((r) => r[key]), value);
  return p == null ? null : p * 100;
}

// 数值数组中位数（忽略非有限值），空序列返回 null。
export function median(xs) {
  const s = (xs || []).filter(Number.isFinite).sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : null;
}

// 按 bands（须按 min 降序排列）找到第一个 min <= score 的档位；
// score 为 null 返回 null。例：[{min:60},{min:40},{min:0}] → 60/40 分档。
export function bandFor(score, bands) {
  if (score == null || !Number.isFinite(score)) return null;
  return bands.find((b) => score >= b.min) || bands[bands.length - 1];
}

// 0–100 分数的直方图：等宽 nBuckets 桶，返回 [{lo, hi, count}]。
// 只统计有限分数，用于每页顶部的得分分布图。
export function histogram(scores, nBuckets = 10) {
  const out = [];
  for (let i = 0; i < nBuckets; i++) out.push({ lo: i * 10, hi: (i + 1) * 10, count: 0 });
  for (const s of scores || []) {
    if (!Number.isFinite(s)) continue;
    const i = Math.min(nBuckets - 1, Math.max(0, Math.floor(s / 10)));
    out[i].count++;
  }
  return out;
}

// 分数组的 tone：posEnd=true 表示高分=好（动量/资金/估值），否则高分=差（风险）。
// 用于直方图按桶着色：中间琥珀、两端红/绿。
export function histTone(i, n, posEnd) {
  const seg = i / Math.max(1, n - 1);
  return posEnd ? (seg >= 0.6 ? "pos" : seg >= 0.3 ? "warn" : "neg")
    : (seg >= 0.6 ? "neg" : seg >= 0.3 ? "warn" : "pos");
}
