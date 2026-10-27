// 流动性·交易成本 Tab：Amihud 非流动性 = |日收益| ÷ 美元成交额（×1e9 缩放，
// 读作「每 $1B 成交的价格冲击」），市场口径取截面中位数；另附流动性-波动 nexus
// （标准化叠加看耦合）与最差/最好流动性标的截面（/risk/liquidity，窗口固定 60 日口径）。
import { useEffect, useMemo, useState } from "react";
import LineChart from "../LineChart.jsx";
import {
  riskFetch, toLine, flatLine, zScoreLine, num, signed, pct0, pct1, il3, dvol,
} from "../../../lib/us/riskUtils";

// 体制 = 市场非流动性（全历史分位）：低分位=冲击小/交易便宜；高分位=冲击大/交易贵。
function regime(stats) {
  if (!stats) return { key: "n/a", label: "—", tone: "", desc: "无数据" };
  const il = num(stats.market_illiq);
  const ilP = num(stats.market_illiq_pctile);
  const nx = num(stats.corr_illiq_vol);
  if (il == null || ilP == null)
    return { key: "neutral", label: "中性", tone: "", desc: "流动性数据不足。" };
  const r = ilP < 0.33 ? { key: "liquid", label: "流动性宽裕", tone: "pos" }
    : ilP < 0.67 ? { key: "normal", label: "流动性正常", tone: "" }
    : { key: "stress", label: "流动性紧张", tone: "neg" };
  const ilWord = ilP < 0.33 ? "冲击低·交易便宜" : ilP < 0.67 ? "冲击中性" : "冲击高·交易昂贵";
  const nxWord = nx != null && nx > 0.5 ? "；波动↑时冲击骤升（流动性-波动强耦合）"
    : nx != null && nx > 0 ? "；波动↑时冲击上升" : "";
  const desc = `市场非流动性 ${il3(il)} / $1B（全历史 ${(ilP * 100).toFixed(0)}% 分位，${ilWord}）${nxWord}。`;
  return { key: r.key, label: r.label, tone: r.tone, desc };
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

// 截面小表：标的 / 冲击每 $1B / 日均成交 / 年化收益
function CsTable({ title, tone, rows }) {
  return (
    <div>
      <div className={tone} style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr className="muted">
            <th style={{ textAlign: "left", padding: "2px 4px" }}>标的</th>
            <th style={{ textAlign: "right", padding: "2px 4px" }}>冲击/$1B</th>
            <th style={{ textAlign: "right", padding: "2px 4px" }}>日均成交</th>
            <th style={{ textAlign: "right", padding: "2px 4px" }}>年化收益</th>
          </tr>
        </thead>
        <tbody>
          {(rows || []).map((r) => (
            <tr key={r.symbol} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <td style={{ padding: "2px 4px", fontWeight: 600 }}>{r.symbol}</td>
              <td style={{ padding: "2px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{il3(r.illiq)}</td>
              <td style={{ padding: "2px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{dvol(r.dvol)}</td>
              <td style={{ padding: "2px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}
                className={num(r.ret) >= 0 ? "pos" : "neg"}>{pct1(r.ret)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function LiquidityTab({ mk = "us" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null); setErr("");
    riskFetch("/risk/liquidity")
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setErr(e.message || String(e)); });
    return () => { alive = false; };
  }, []);

  const reg = useMemo(() => regime(data), [data]);
  // nexus：两条线均标准化为均值 0/标准差 1（illiq 与 vol 量纲不同，标准化后看协同运动）
  const nexusLine = useMemo(() => (data ? {
    illiq: zScoreLine(toLine(data.market_illiq_series)),
    vol: zScoreLine(toLine(data.mkt_vol_series)),
  } : null), [data]);

  if (err) return <div className="card neg" style={{ fontSize: 13 }}>流动性数据加载失败：{err}</div>;
  if (!data) return <div className="spinner">加载流动性数据中…</div>;

  const illiqLine = toLine(data.market_illiq_series);
  const band = (key) => (data.illiq_pcts?.[key] == null ? []
    : flatLine(data.market_illiq_series, data.illiq_pcts[key]));

  const ilP = num(data.market_illiq_pctile);
  const nx = num(data.corr_illiq_vol);
  const irc = num(data.illiq_ret_corr);
  const worst = data.most_illiquid?.[0];
  const best = data.most_liquid?.[0];

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        流动性 / 交易成本（{data.n_names} 只标的，{data.n_days} 个交易日，滚动 {data.window} 日）。
        回答「<b>现在交易贵不贵、谁最难进出</b>」。Amihud = mean(|r| ÷ 美元成交额)，
        单位 = 每 $1B 成交的价格冲击（收益率）；值越大交易越贵。市场口径取截面中位数（对薄票长尾稳健）。
      </div>

      <div className={`card ${reg.tone}`} style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ fontSize: 26, fontWeight: 700 }} className={reg.tone}>{reg.label}</div>
        <div className="muted" style={{ flex: 1, minWidth: 260, fontSize: 12 }}>{reg.desc}</div>
      </div>

      <div className="stats" style={{ flexWrap: "wrap" }}>
        <Stat label="市场非流动性" value={`${il3(data.market_illiq)} / $1B`}
          tone={ilP != null ? (ilP >= 0.67 ? "neg" : ilP < 0.33 ? "pos" : "") : ""}
          sub={`全历史 ${pct0(data.market_illiq_pctile)} 分位`} />
        <Stat label="流动性-波动相关性" value={signed(data.corr_illiq_vol, 3)}
          tone={nx != null && nx > 0.6 ? "warn" : ""} sub="波动↑时冲击↑（正=同紧缩）" />
        <Stat label="非流动性溢价" value={signed(data.illiq_ret_corr, 3)}
          tone={irc != null ? (irc > 0 ? "pos" : "neg") : ""} sub="Spearman(冲击, 收益)；正=难交易者补偿高" />
        <Stat label="市场波动率" value={pct1(data.mkt_vol)} sub="等权·年化（上下文）" />
        <Stat label="最差流动性标的" value={worst ? worst.symbol : "—"}
          sub={worst ? `${il3(worst.illiq)} / $1B · ${dvol(worst.dvol)}/日` : ""} />
        <Stat label="最流动性标的" value={best ? best.symbol : "—"}
          sub={best ? `${il3(best.illiq)} / $1B · ${dvol(best.dvol)}/日` : ""} />
      </div>

      <div className="card">
        <h3>市场非流动性（Amihud，截面中位数）· 全历史分位带</h3>
        <LineChart series={[
          { data: illiqLine, color: "#ef5350", lineWidth: 2 },
          { data: band("p75"), color: "rgba(239,83,80,0.4)", lineWidth: 1 },
          { data: band("p50"), color: "rgba(154,166,178,0.4)", lineWidth: 1 },
          { data: band("p25"), color: "rgba(102,187,106,0.4)", lineWidth: 1 },
        ]} height={210} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          红线=市场非流动性；灰=全历史中位、绿=25% 分位（宽裕）、暗红=75% 分位（紧张）。
          飙升 = 交易成本恶化（危机/恐慌）。
        </div>
      </div>

      <div className="card">
        <h3>流动性-波动 nexus（标准化叠加）</h3>
        {nexusLine && nexusLine.illiq.length > 1 ? (
          <LineChart series={[
            { data: nexusLine.illiq, color: "#ef5350", lineWidth: 2 },
            { data: nexusLine.vol, color: "#ab47bc", lineWidth: 1.5 },
          ]} height={210} />
        ) : <div className="muted" style={{ fontSize: 11 }}>数据不足</div>}
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          两条线均标准化为均值 0/标准差 1。红=非流动性、紫=波动率。同向上行 = 流动性-波动耦合
          （corr_illiq_vol 正）——最需要流动性时，冲击与波动齐升。
        </div>
      </div>

      <div className="card">
        <h3>截面：最差 vs 最好流动性标的（全历史均值）</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 4 }}>
          <CsTable title="▲ 最差流动性（冲击最高，交易最贵）" tone="neg" rows={data.most_illiquid} />
          <CsTable title="▼ 最好流动性（冲击最低，交易最便宜）" tone="pos" rows={data.most_liquid} />
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          左=非流动性最高（小盘/薄量）；右=非流动性最低（大盘/厚量）。冲击随美元成交额递减——规模与流动性同向。
        </div>
      </div>

      <div className="card">
        <b>口径说明</b>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          Amihud = |收益| ÷ 美元成交额 的滚动均值（逐票滚动 {data.window} 日、截面取中位数），
          数值 ×1e9 缩放。流动性-波动相关性 {signed(data.corr_illiq_vol, 3)}：越接近 +1，
          「波动来时交易越贵」越显著（与有效下注数的负相关互为表里）。
        </div>
      </div>
    </div>
  );
}
