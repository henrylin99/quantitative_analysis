// 有效下注数·可分散性 Tab：N 只股票里到底有几个独立风险源、分散化现在还有效吗。
// 数据来自 /risk/effbets?window=（后端免特征分解闭式 eff_bets = N²/Σρ²ᵢⱼ，
// 平均两两相关 ρ̄、单因子上界、聚集比 = eff_bets/上界，及匹配窗口的市场波动序列）。
// 有效下注数低 = 齐涨齐跌/分散失效（宏观市）；高 = 个股分化（选股市）。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../LineChart.jsx";
import {
  riskFetch, toLine, flatLine, ratioLine, num, signed, pct0, pct1,
} from "../../../lib/us/riskUtils";

const WINDOW_OPTS = [40, 60, 90, 126];

// 体制 = 下注体制（全历史分位）× 聚集体制（聚集比水平）。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const eb = num(stats.eff_bets);
  const ebP = num(stats.eff_bets_pctile);
  const cr = num(stats.cluster_ratio);
  if (eb == null || ebP == null)
    return { key: "neutral", label: "中性", tone: "", desc: "有效下注数数据不足。" };
  const bets = ebP < 0.33 ? { key: "concentrated", label: "风险集中", tone: "neg" }
    : ebP < 0.67 ? { key: "balanced", label: "均衡", tone: "" }
    : { key: "diverse", label: "分散有效", tone: "pos" };
  const cl = cr == null ? { key: "na", label: "—", tone: "" }
    : cr < 0.15 ? { key: "clustered", label: "板块高度聚集", tone: "neg" }
    : cr < 0.30 ? { key: "moderate", label: "中度聚集", tone: "warn" }
    : { key: "uniform", label: "接近均匀", tone: "pos" };
  const rank = { neg: 3, warn: 2, pos: 1, "": 0 };
  const tone = rank[bets.tone] >= rank[cl.tone] ? bets.tone : cl.tone;
  const ebWord = ebP >= 0.67 ? "来源多·分散有效" : ebP < 0.33 ? "来源少·风险集中" : "中性";
  const clWord = cl.key === "clustered" ? "板块/因子高度聚集（远低于单因子上界）"
    : cl.key === "moderate" ? "存在板块聚集" : "相关性接近均匀";
  const desc = `有效下注数 ${eb.toFixed(1)} / ${stats.n_names ?? "—"}（全历史 ${(ebP * 100).toFixed(0)}% 分位，${ebWord}）；${clWord}。`;
  return { key: `${bets.key}_${cl.key}`, label: `${bets.label} · ${cl.label}`, tone, desc };
}

function Stat({ label, value, tone = "", sub = "" }) {
  return (
    <div className="stat">
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div className={tone} style={{ fontSize: 18, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      {sub && <div className="muted" style={{ fontSize: 10 }}>{sub}</div>}
    </div>
  );
}

const betsTone = (p) => (num(p) == null ? "" : p >= 0.67 ? "pos" : p < 0.33 ? "neg" : "");
const rhoTone = (v) => (num(v) == null ? "" : v >= 0.3 ? "neg" : v < 0.1 ? "pos" : "");
const clTone = (v) => {
  const x = num(v);
  if (x == null) return "";
  return x < 0.15 ? "neg" : x < 0.3 ? "warn" : "pos";
};

export default function EffBetsTab() {
  const [data, setData] = useState(null);
  const [window_, setWindow] = useState(60);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null); setErr("");
    riskFetch("/risk/effbets", { window: window_ })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message || String(e)); });
    return () => { alive = false; };
  }, [window_]);

  const reg = useMemo(() => regime(data), [data]);
  // 聚集比序列纯客户端派生：eff_bets ÷ 单因子上界（时间对齐）
  const clusterLine = useMemo(() => (data
    ? ratioLine(toLine(data.eff_bets_series), toLine(data.sf_ceiling_series))
    : []), [data]);

  if (err) return <div className="card neg" style={{ fontSize: 13 }}>有效下注数数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载有效下注数数据中…</div>;

  const effLine = toLine(data.eff_bets_series);
  const rhoLine = toLine(data.rho_bar_series);
  const sfLine = toLine(data.sf_ceiling_series);
  const band = (val) => (val == null ? [] : flatLine(data.eff_bets_series, val));
  const ebP = num(data.eff_bets_pctile);
  const cbv = num(data.corr_bets_vol);

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        有效下注数 / 可分散性（{data.n_names} 只标的，{data.n_days} 个交易日，滚动 {data.window} 日相关）。
        回答「<b>N 只股票里到底有几个独立风险源、分散化现在还有效吗</b>」。
        恒等式：有效下注数 = (Σλ)²/Σλ² = N²/Σρ²ᵢⱼ（特征值迹=N，无需特征分解）；
        由 x² 凸性，真实值恒 ≤ 单因子上界。
      </div>

      <div className={`card ${reg.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 26, fontWeight: 700 }} className={reg.tone}>{reg.label}</div>
        <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{reg.desc}</div>
      </div>

      <div className="stats" style={{ flexWrap: "wrap" }}>
        <Stat label="有效下注数" value={`${data.eff_bets != null ? data.eff_bets.toFixed(1) : "—"} / ${data.n_names}`}
          tone={betsTone(ebP)} sub={`全历史 ${pct0(data.eff_bets_pctile)} 分位`} />
        <Stat label="平均相关系数" value={signed(data.rho_bar, 3)} tone={rhoTone(data.rho_bar)}
          sub={`全历史 ${pct0(data.rho_pctile)} 分位`} />
        <Stat label="单因子上界" value={data.sf_ceiling != null ? data.sf_ceiling.toFixed(1) : "—"}
          sub="给定 ρ̄ 的 eff_bets 理论上界" />
        <Stat label="聚集比" value={pct1(data.cluster_ratio)} tone={clTone(data.cluster_ratio)}
          sub="有效下注数 ÷ 上界" />
        <Stat label="市场波动率" value={pct1(data.mkt_vol)} sub="等权·年化（上下文）" />
        <Stat label="下注-波动相关性" value={signed(data.corr_bets_vol, 3)}
          tone={cbv != null && cbv < -0.5 ? "neg" : ""} sub="波动↑时下注数↓（负=分散失效）" />
      </div>

      <div className="card">
        <h3>有效下注数（独立风险源数）· 全历史分位带</h3>
        <LineChart series={[
          { data: effLine, color: "#26a69a", lineWidth: 2 },
          { data: band(data.eff_bets_pcts?.p75), color: "rgba(239,83,80,0.5)", lineWidth: 1 },
          { data: band(data.eff_bets_pcts?.p50), color: "rgba(154,166,178,0.45)", lineWidth: 1 },
          { data: band(data.eff_bets_pcts?.p25), color: "rgba(102,187,106,0.5)", lineWidth: 1 },
        ]} height={210} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          绿线=全历史 25% 分位、灰线=中位、红线=75% 分位。危机时骤降至个位数（齐涨齐跌）；分散时升高（选股市）。
        </div>
      </div>

      <div className="card">
        <h3>平均两两相关系数 ρ̄（精确）</h3>
        <LineChart data={rhoLine} color="#ff9800" height={190} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          N(N−1)/2 对相关系数的精确平均。→1=齐涨齐跌；接近 0=各自独立。
        </div>
      </div>

      <div className="card">
        <h3>聚集比（有效下注数 ÷ 单因子上界）</h3>
        <LineChart data={clusterLine} color="#ab47bc" height={190} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          ∈(0,1]。低 = 相关性远非均匀、板块/因子强烈聚集（独立来源被板块结构吞噬）；→1 = 接近单因子均匀。
        </div>
      </div>

      <div className="card">
        <h3>有效下注数 vs 单因子上界（差距 = 板块聚集度）</h3>
        <LineChart series={[
          { data: sfLine, color: "rgba(120,144,156,0.7)", lineWidth: 1.5 },
          { data: effLine, color: "#26a69a", lineWidth: 2 },
        ]} height={210} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          灰=单因子上界（ρ̄ 下 eff_bets 的最大可能）；绿=真实有效下注数。两条线的差距即板块/因子聚集吞噬掉的
          独立下注——差距越大，「平均相关看着低」越是假象。
        </div>
      </div>

      <div className="card" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <b>相关窗口</b>
        <select value={window_} onChange={(e) => setWindow(+e.target.value)}>
          {WINDOW_OPTS.map((w) => <option key={w} value={w}>{w} 日</option>)}
        </select>
        <span className="muted" style={{ fontSize: 11 }}>
          滚动相关窗口越短越敏感、越长越平滑。下注-波动相关性 {signed(data.corr_bets_vol, 3)}：
          负值越大，「最需要分散时分散越失效」越显著。
        </span>
      </div>
    </div>
  );
}
