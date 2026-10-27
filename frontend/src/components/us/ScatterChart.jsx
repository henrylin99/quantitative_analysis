import { useEffect, useRef, useState } from "react";

const p2 = (x) => {
  if (x == null || Number.isNaN(x)) return "—";
  const a = Math.abs(x);
  if (a >= 1e12) return (x / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return (x / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (x / 1e6).toFixed(2) + "M";
  if (a >= 1e4) return (x / 1e3).toFixed(1) + "K";
  return Number(x).toFixed(2);
};

/**
 * A plain X-Y scatter plot — the one chart shape lightweight-charts can't draw,
 * because its horizontal axis is time, not an arbitrary numeric domain. Rendered
 * on a dedicated canvas: light grid + tick labels, one dot per point, coloured by
 * the caller (e.g. green/red for up/down day). A hovering pointer snaps to the
 * nearest dot and surfaces its label/value in a DOM tooltip.
 *
 * points: [{ x, y, symbol, color?, size? }]  (rows with null/NaN x or y are skipped)
 */
export default function ScatterChart({ points = [], curve = [], xLabel = "", yLabel = "", height = 320, regression = true }) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const [hover, setHover] = useState(null);
  const layoutRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current, wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = wrap.clientWidth, h = height;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const xs = [...points, ...curve].map((p) => p.x).filter((v) => v != null && !Number.isNaN(v));
      const ys = [...points, ...curve].map((p) => p.y).filter((v) => v != null && !Number.isNaN(v));
      if (!xs.length || !ys.length) { layoutRef.current = null; return; }
      let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      if (x1 === x0) x1 = x0 + 1;
      if (y1 === y0) y1 = y0 + 1;
      const L = 46, R = 12, T = 12, B = 30;
      const sx = (x) => L + ((x - x0) / (x1 - x0)) * (w - L - R);
      const sy = (y) => h - B - ((y - y0) / (y1 - y0)) * (h - T - B);
      layoutRef.current = { sx, sy, w, h };

      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.fillStyle = "#6b7785";
      ctx.font = "10px sans-serif";
      ctx.lineWidth = 1;
      const ticks = (a, b, n) => Array.from({ length: n + 1 }, (_, i) => a + ((b - a) * i) / n);
      ctx.textAlign = "right"; ctx.textBaseline = "middle";
      for (const tv of ticks(y0, y1, 4)) {
        const yy = sy(tv);
        ctx.beginPath(); ctx.moveTo(L, yy); ctx.lineTo(w - R, yy); ctx.stroke();
        ctx.fillText(p2(tv), L - 6, yy);
      }
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      for (const tv of ticks(x0, x1, 6)) {
        const xx = sx(tv);
        ctx.beginPath(); ctx.moveTo(xx, T); ctx.lineTo(xx, h - B); ctx.stroke();
        ctx.fillText(p2(tv), xx, h - B + 5);
      }
      // axis titles
      ctx.fillStyle = "#9aa6b2";
      ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillText(yLabel, 4, 2);
      ctx.textAlign = "right"; ctx.textBaseline = "bottom"; ctx.fillText(xLabel, w - R, h - 2);

      // optional connected curve (e.g. the efficient-frontier hyperbola) — drawn
      // under the dots so member points stay on top.
      if (curve && curve.length >= 2) {
        ctx.strokeStyle = "rgba(255,152,0,0.9)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        let started = false;
        for (const p of curve) {
          if (p.x == null || Number.isNaN(p.x) || p.y == null || Number.isNaN(p.y)) continue;
          const X = sx(p.x), Y = sy(p.y);
          if (!started) { ctx.moveTo(X, Y); started = true; } else ctx.lineTo(X, Y);
        }
        ctx.stroke();
      }

      for (const p of points) {
        if (p.x == null || Number.isNaN(p.x) || p.y == null || Number.isNaN(p.y)) continue;
        ctx.fillStyle = p.color || "rgba(79,147,231,0.7)";
        ctx.beginPath();
        ctx.arc(sx(p.x), sy(p.y), p.size || 3, 0, Math.PI * 2);
        ctx.fill();
      }

      // least-squares regression line + Pearson r: the linear relationship the dots
      // encode, drawn across the full X domain. Same math as the correlation matrix.
      const valid = points.filter((p) => p.x != null && !Number.isNaN(p.x) && p.y != null && !Number.isNaN(p.y));
      if (regression && valid.length >= 3) {
        let Sx = 0, Sy = 0, Sxx = 0, Sxy = 0;
        for (const p of valid) { Sx += p.x; Sy += p.y; Sxx += p.x * p.x; Sxy += p.x * p.y; }
        const denom = valid.length * Sxx - Sx * Sx;
        if (denom !== 0) {
          const slope = (valid.length * Sxy - Sx * Sy) / denom;
          const intercept = (Sy - slope * Sx) / valid.length;
          const mx = Sx / valid.length, my = Sy / valid.length;
          let num = 0, dx2 = 0, dy2 = 0;
          for (const p of valid) { const a = p.x - mx, b = p.y - my; num += a * b; dx2 += a * a; dy2 += b * b; }
          const r = dx2 && dy2 ? num / Math.sqrt(dx2 * dy2) : 0;
          const yAt = (x) => slope * x + intercept;
          ctx.strokeStyle = "rgba(255,193,7,0.85)";
          ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(sx(x0), sy(yAt(x0))); ctx.lineTo(sx(x1), sy(yAt(x1))); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = "#ffc107"; ctx.font = "bold 11px sans-serif";
          ctx.textAlign = "right"; ctx.textBaseline = "top";
          ctx.fillText(`r = ${r.toFixed(2)}`, w - R - 2, T + 2);
        }
      }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [points, curve, xLabel, yLabel, height]);

  const onMove = (e) => {
    const lay = layoutRef.current;
    if (!lay) { setHover(null); return; }
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let best = null, bd = 14 * 14;
    for (const p of points) {
      if (p.x == null || Number.isNaN(p.x) || p.y == null || Number.isNaN(p.y)) continue;
      const dx = lay.sx(p.x) - mx, dy = lay.sy(p.y) - my, d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = p; }
    }
    setHover(best ? { ...best, px: lay.sx(best.x), py: lay.sy(best.y), w: lay.w } : null);
  };

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%", height }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <canvas ref={canvasRef} className="scatter-canvas" style={{ display: "block" }} />
      {hover && (
        <div
          className="scatter-tip"
          style={{ left: Math.min(hover.px + 8, hover.w - 110), top: Math.max(hover.py - 36, 0) }}
        >
          <b>{hover.symbol}</b> <span className="muted">{xLabel} {p2(hover.x)} · {yLabel} {p2(hover.y)}</span>
        </div>
      )}
    </div>
  );
}
