import { useEffect, useRef } from "react";
import { createChart, LineSeries, ColorType } from "lightweight-charts";

/**
 * Single- or multi-series line chart. Pass `data` + `color` for one line, or
 * `series: [{ data, color, lineWidth?, label? }]` to overlay several (e.g. a
 * strategy-equity comparison). Series are torn down and rebuilt on every data
 * change so the line count can vary between renders.
 */
export default function LineChart({ data = [], color = "#4f93e7", series, height = 180 }) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const seriesArrRef = useRef([]);

  useEffect(() => {
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#9aa6b2", fontSize: 11 },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      timeScale: { borderColor: "rgba(255,255,255,0.1)" },
    });
    chartRef.current = chart;
    return () => chart.remove();
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const s of seriesArrRef.current) { try { chart.removeSeries(s); } catch (_) { /* already gone */ } }
    seriesArrRef.current = [];
    const list = series && series.length ? series : [{ data, color }];
    for (const item of list) {
      const opts = { color: item.color || color, lineWidth: item.lineWidth || 2, priceLineVisible: false };
      if (list.length > 1) opts.lastValueVisible = false; // de-clutter overlapping curves
      const s = chart.addSeries(LineSeries, opts);
      s.setData(item.data || []);
      seriesArrRef.current.push(s);
    }
    if (list.some((it) => (it.data || []).length)) chart.timeScale().fitContent();
  }, [data, color, series]);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
