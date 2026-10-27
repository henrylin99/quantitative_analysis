// 波动率锥 tab —— /market/volcone（路由未暴露 symbol/window 参数，返回服务端默认标的的
// 全窗口锥 + 全市场排名）。口径移植自开源参考实现的 VolConePage：
// 各回看窗口(10..252日)实现波动率 vs 自身全历史分位带（min/p10/p25/p50/p75/p90/max）。
import { useEffect, useMemo, useState } from "react";
import { fetchUsAnalytics } from "../../../api/usAnalytics";
import LineChart from "../LineChart.jsx";
import { Stat, ChartCard, RegimeBanner } from "./shared.jsx";
import {
  toLine, sortRows, vol1, pct0, signedPct1, num,
} from "../../../lib/us/analyticsFmt";

const WIN_OPTS = [10, 20, 30, 60, 90, 120, 180, 252];

// 按历史分位着色（高=剧烈=neg、低=平静=pos）。
const pctTone = (p) => (p == null ? "" : p >= 0.8 ? "neg" : p <= 0.2 ? "pos" : "");

// 体制 = 参考窗口(20日)当前波动的历史分位 × 期限结构(10日 vs 120日)。
function regime(si) {
  if (!si || !si.cone || !si.cone.length) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const cone = si.cone;
  const ref = cone.find((c) => c.window === 20) || null;
  if (!ref) return { key: "neutral", label: "数据不足", tone: "", desc: "参考窗口(20日)数据不足。" };
  const pct = num(ref.pctile);
  const cur = num(ref.current);
  if (pct == null || cur == null)
    return { key: "neutral", label: "数据不足", tone: "", desc: "波动分位数据不足。" };
  const vol = pct < 0.2 ? { label: "历史低位" } : pct < 0.4 ? { label: "偏低" }
    : pct < 0.6 ? { label: "中性" } : pct < 0.8 ? { label: "偏高" } : { label: "历史高位" };
  const c10 = cone.find((c) => c.window === 10), c120 = cone.find((c) => c.window === 120);
  let tsLabel = "期限结构平坦";
  if (c10 && c120) {
    const diff = num(c10.current) - num(c120.current);
    if (diff != null && Math.abs(diff) > 0.01)
      tsLabel = diff > 0 ? "前端飙升" : "后端偏高";
  }
  const tone = pct >= 0.8 ? "neg" : pct <= 0.2 ? "pos" : "";
  const volWord = pct >= 0.8 ? "历史性高波动" : pct >= 0.6 ? "偏高" : pct >= 0.4 ? "中性" : "偏低";
  return {
    key: vol.label + "_" + tsLabel,
    label: vol.label + " · " + tsLabel, tone,
    desc: `${si.symbol} 当前 20 日年化波动 ${(cur * 100).toFixed(1)}%，处自身历史 ${(pct * 100).toFixed(0)}% 分位（${volWord}）。`,
    pctile: pct, current: cur,
  };
}

// 一行锥形横条：[p_min..p_max] 底条 + p25–p75 着色块 + 中位竖线 + 当前值彩色竖标。
function ConeBar({ row }) {
  const lo = num(row.p_min), hi = num(row.p_max);
  const span = lo != null && hi != null && hi > lo ? hi - lo : 1;
  const pos = (v) => (v == null ? 0 : Math.max(0, Math.min(100, ((v - lo) / span) * 100)));
  const p25 = pos(row.p25), p75 = pos(row.p75), cur = pos(row.current);
  return (
    <div style={{ position: "relative", height: 16, background: "rgba(255,255,255,0.05)", borderRadius: 3 }}>
      <div style={{ position: "absolute", top: 2, bottom: 2, left: p25 + "%", width: (p75 - p25) + "%",
        background: "rgba(154,166,178,0.30)", borderRadius: 2 }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: pos(row.p50) + "%", width: 1,
        background: "rgba(154,166,178,0.7)" }} />
      <div title={`当前 ${vol1(row.current)} · 分位 ${pct0(row.pctile)}`}
        style={{ position: "absolute", top: -2, bottom: -2, left: `calc(${cur}% - 1.5px)`, width: 3,
          background: row.pctile >= 0.8 ? "#ef5350" : row.pctile <= 0.2 ? "#26a69a" : "#fff",
          borderRadius: 2, boxShadow: "0 0 4px rgba(0,0,0,0.6)" }} />
    </div>
  );
}

export default function VolConeTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [win, setWin] = useState(20);
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  useEffect(() => {
    let on = true;
    setErr("");
    fetchUsAnalytics("/market/volcone")
      .then((d) => { if (on) setData(d); })
      .catch((e) => { if (on) setErr(String(e?.message || e)); });
    return () => { on = false; };
  }, []);

  const si = data?.symbol_info || null;
  const ranking = useMemo(() => data?.ranking || [], [data]);
  const vd = useMemo(() => regime(si), [si]);
  const sorted = useMemo(() => sortRows(ranking, sortKey, sortDir), [ranking, sortKey, sortDir]);

  if (err) return <div className="spinner">波动率锥数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载波动率锥数据中…</div>;

  const cone = si?.cone || [];
  const ref = cone.find((c) => c.window === 20) || null;
  const top = ranking.slice(0, 5);
  const bottom = [...ranking].slice(-5).reverse();

  // 时序图：所选窗口实现波动率 + 该窗口 p10/p25/p50/p75/p90 历史分位横线。
  const volLine = si ? toLine(si.vol_series) : [];
  const tsRow = cone.find((c) => c.window === win) || null;
  const band = (val) => (val == null || !volLine.length
    ? [] : [{ time: volLine[0].time, value: val }, { time: volLine[volLine.length - 1].time, value: val }]);

  const toggleSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "name" ? "asc" : "desc"); }
  };
  const arrow = (k) => (k === sortKey ? (sortDir === "asc" ? " ▲" : " ▼") : "");
  const slope = (() => {
    const a = cone.find((c) => c.window === 10), b = cone.find((c) => c.window === 120);
    return a && b ? num(a.current) - num(b.current) : null;
  })();

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        波动率锥（{data.n_names} 只标的，{data.n_days} 个交易日）。对 8 个回看窗口（10…252 日）各算实现波动率，
        用<b>每个窗口自身全历史</b>的分位带做锥，叠<b>当前</b>值与历史分位——期权式的波动率贵/便宜期限结构。
        区别于「波动率体制」——那页是<b>单窗口</b>的<b>市场</b>动荡时序；本页是<b>多窗口</b>的<b>个股</b>快照。
        （示例标的由服务端固定，排名表覆盖全市场。）
      </div>

      <RegimeBanner label={si ? `${si.symbol} · ${vd.label}` : vd.label} tone={vd.tone} desc={vd.desc} />

      {/* 锥快照表（头条）：逐窗口一行，横条并排呈锥形 */}
      <div className="card" style={{ marginBottom: 12 }}>
        <h3 style={{ marginBottom: 6 }}>{si ? si.symbol : ""} 实现波动率锥 · 当前值 vs 各窗口自身历史分位</h3>
        <table className="data" style={{ width: "100%" }}>
          <thead><tr>
            <th style={{ width: 70 }}>窗口</th>
            <th style={{ width: 96 }}>当前波动</th>
            <th>分布 [min … p25 … 中位 … p75 … max]（竖条=当前）</th>
            <th style={{ width: 84 }}>历史分位</th>
            <th style={{ width: 60 }}>样本</th>
          </tr></thead>
          <tbody>
            {cone.map((r) => (
              <tr key={r.window}>
                <td><b>{r.window}日</b></td>
                <td className={pctTone(r.pctile)} style={{ fontVariantNumeric: "tabular-nums" }}>{vol1(r.current)}</td>
                <td><ConeBar row={r} /></td>
                <td className={pctTone(r.pctile)} style={{ fontVariantNumeric: "tabular-nums" }}>{pct0(r.pctile)}</td>
                <td className="muted">{r.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          灰块 = 历史 25%–75% 分位、竖灰线 = 中位数、彩色竖条 = 当前值（红=历史高位/绿=历史低位）。
          期限越长分布越窄 → 横条由宽到窄即「锥」。
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 12 }}>
        <ChartCard title="个股实现波动率时序 · 窗口可调"
          desc="所选窗口的年化实现波动率（红），叠加该窗口全历史 p10/p25/中位/p75/p90 横线带——当前红线的相对位置即动荡程度。">
          <div style={{ marginBottom: 6 }}>
            <select value={win} onChange={(e) => setWin(+e.target.value)}>
              {WIN_OPTS.map((w) => <option key={w} value={w}>{w} 日</option>)}
            </select>
          </div>
          {volLine.length ? (
            <LineChart series={[
              { data: volLine, color: "#ef5350", lineWidth: 2 },
              { data: band(tsRow?.p90), color: "rgba(239,83,80,0.45)", lineWidth: 1 },
              { data: band(tsRow?.p75), color: "rgba(239,83,80,0.30)", lineWidth: 1 },
              { data: band(tsRow?.p50), color: "rgba(154,166,178,0.45)", lineWidth: 1 },
              { data: band(tsRow?.p25), color: "rgba(102,187,106,0.30)", lineWidth: 1 },
              { data: band(tsRow?.p10), color: "rgba(102,187,106,0.45)", lineWidth: 1 },
            ]} height={220} />
          ) : <div className="muted" style={{ fontSize: 12 }}>无波动率时序。</div>}
        </ChartCard>

        {si && ref && (
          <div className="card" style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center" }}>
            <b style={{ fontSize: 16 }}>{si.symbol}</b>
            <span className="muted">{si.name}</span>
            <Stat label="20日当前波动" value={vol1(ref.current)} tone={pctTone(ref.pctile)} />
            <Stat label="历史分位" value={pct0(ref.pctile)} sub="20日窗口" />
            <Stat label="历史最低" value={vol1(ref.p_min)} sub="20日窗口" />
            <Stat label="中位数" value={vol1(ref.p50)} sub="20日窗口" />
            <Stat label="历史最高" value={vol1(ref.p_max)} sub="20日窗口" />
            <Stat label="期限斜率" value={signedPct1(slope)} sub="10日−120日" />
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12, margin: "12px 0" }}>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>历史高位波动 Top 5（20日分位最高）</h3>
          {top.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name} · {vol1(r.current_vol)}</span></span>
              <span className="neg">分位 {pct0(r.pctile)}</span>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 6 }}>历史低位波动 Bottom 5（20日分位最低）</h3>
          {bottom.map((r) => (
            <div key={r.symbol} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
              <span><b>{r.symbol}</b> <span className="muted" style={{ fontSize: 11 }}>{r.name} · {vol1(r.current_vol)}</span></span>
              <span className="pos">分位 {pct0(r.pctile)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>全市场波动率锥排名 · 按 20 日历史分位降序（rank 1 = 当前最处于历史高位）</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr>
              <th onClick={() => toggleSort("rank")}>#{arrow("rank")}</th>
              <th onClick={() => toggleSort("symbol")}>代码{arrow("symbol")}</th>
              <th onClick={() => toggleSort("name")}>名称{arrow("name")}</th>
              <th onClick={() => toggleSort("current_vol")}>当前波动@20{arrow("current_vol")}</th>
              <th onClick={() => toggleSort("pctile")}>历史分位@20{arrow("pctile")}</th>
              <th onClick={() => toggleSort("slope")}>期限斜率{arrow("slope")}</th>
              <th onClick={() => toggleSort("n")}>样本{arrow("n")}</th>
            </tr></thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol}>
                  <td className="muted">{r.rank}</td>
                  <td><b>{r.symbol}</b></td>
                  <td className="muted">{r.name}</td>
                  <td className={pctTone(r.pctile)}>{vol1(r.current_vol)}</td>
                  <td className={pctTone(r.pctile)}>{pct0(r.pctile)}</td>
                  <td className={r.slope != null && r.slope > 0 ? "neg" : r.slope != null && r.slope < 0 ? "" : "muted"}>{signedPct1(r.slope)}</td>
                  <td className="muted">{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
