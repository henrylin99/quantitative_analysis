// 市场统计 8 个 tab 共用的格式化 / 时序投影工具（从开源参考实现的 lib 纯函数移植）。
// 仅本目录新文件使用，不改动 lib/us/ 下既有文件。

/** 归一时间到 unix 秒：兼容 unix 秒 / unix 毫秒 / 'YYYY-MM-DD' 字符串。 */
export function normTime(t) {
  if (t == null) return null;
  if (typeof t === "number") {
    if (!Number.isFinite(t)) return null;
    return t > 1e12 ? Math.floor(t / 1000) : Math.floor(t);
  }
  const s = String(t);
  const ms = Date.parse(s.length === 10 ? `${s}T00:00:00Z` : s);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : null;
}

export const num = (v) => (v == null || !Number.isFinite(+v) ? null : +v);
export const int0 = (v) => (v == null ? "—" : Math.round(v).toString());
export const signed1 = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1));
export const pct0 = (v) => (v == null ? "—" : (v * 100).toFixed(0) + "%");
export const pct1 = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
export const signedPct1 = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%");
export const pctSigned = (v) => (v == null ? "—" : (v * 100 >= 0 ? "+" : "") + (v * 100).toFixed(3) + "%");
export const vol1 = pct1;
export const disp2 = (v) => (v == null ? "—" : (v * 100).toFixed(2) + "%");
export const shr0 = pct0;
export const share1 = pct1;
export const signedShare1 = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%");
export const fixed2 = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2));
export const fixed3 = (v) => (v == null ? "—" : v.toFixed(3));
export const rho = (v) => (v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(3));
export const vr = (v) => (v == null ? "—" : v.toFixed(3));
export const price2 = (v) => (v == null ? "—" : "$" + v.toFixed(2));
export const sharpe = (v, d = 2) => (v == null ? "—" : (+v).toFixed(d));

export const MONTH_LABELS = ["1月", "2月", "3月", "4月", "5月", "6月",
  "7月", "8月", "9月", "10月", "11月", "12月"];
export const DOW_LABELS = ["周一", "周二", "周三", "周四", "周五"];
export const monthLabel = (m) => (m == null || m < 1 || m > 12 ? "—" : MONTH_LABELS[m - 1]);
export const dowLabel = (d) => (d == null || d < 0 || d > 4 ? "—" : DOW_LABELS[d]);

/** series [{time, ...}|{time,value}] → LineChart [{time,value}]，跳过 null/坏时间。 */
export function toLine(series, key) {
  const out = [];
  for (const p of series || []) {
    const v = num(key == null ? p.value : p[key]);
    const t = normTime(p.time);
    if (v != null && t != null) out.push({ time: t, value: v });
  }
  return out;
}

/** 水平参考带：整段时序上画一条 value 常数线。 */
export function bandOn(line, val) {
  if (val == null || !line.length) return [];
  return [{ time: line[0].time, value: val }, { time: line[line.length - 1].time, value: val }];
}

/** ymd 显示（unix 秒 → YYYY-MM-DD）。 */
export const ymd = (t) => (t == null ? "—" : new Date(t * 1000).toISOString().slice(0, 10));

/** 通用表格排序 hook 辅助：无 hook 版，组件里配合 useMemo 用。 */
export function sortRows(rows, sortKey, sortDir) {
  const arr = [...rows];
  arr.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (typeof av === "string" || typeof bv === "string")
      return sortDir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    const diff = (av ?? -Infinity) - (bv ?? -Infinity);
    return sortDir === "asc" ? diff : -diff;
  });
  return arr;
}
