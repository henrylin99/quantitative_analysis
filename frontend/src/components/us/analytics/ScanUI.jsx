// 美股扫描器六维 tab 的共享展示件：分档瓦片、得分直方图、可点选因子
// 桶/旗标 chip、行内旗标。全部 scope 在 .us-tv 深色主题下（父级挂类）。
export const TONE_COLOR = { pos: "var(--tv-up)", neg: "var(--tv-down)", warn: "#f5a623", neutral: "var(--tv-text-dim)" };

// 概览分档瓦片：可点击过滤 + 底部占比堆叠条。
// tiers: [{key,label,tone}]；counts: {key:n}；active: 当前选中 key|null。
export function TierTiles({ tiers, counts, total, active, onToggle, subtitles = {} }) {
  const n = total || 1;
  return (
    <>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {tiers.map((t) => {
          const cnt = counts[t.key] ?? 0;
          const on = active === t.key;
          return (
            <button key={t.key} type="button" data-tier={t.key} data-tier-active={on ? "1" : "0"} data-tier-count={cnt}
              onClick={() => onToggle(on ? null : t.key)}
              style={{
                flex: "1 1 160px", textAlign: "left", padding: "12px 14px",
                background: on ? "var(--tv-bg-elev)" : "var(--tv-bg)",
                border: `1px solid ${on ? TONE_COLOR[t.tone] : "var(--tv-border)"}`,
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: 15, fontWeight: 600, color: TONE_COLOR[t.tone] }}>{t.label}</span>
                <span style={{ fontSize: 22, fontWeight: 700, color: TONE_COLOR[t.tone], fontVariantNumeric: "tabular-nums" }}>{cnt}</span>
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                {((cnt / n) * 100).toFixed(0)}%{subtitles[t.key] ? ` · ${subtitles[t.key]}` : ""}
              </div>
            </button>
          );
        })}
      </div>
      <div style={{ display: "flex", height: 10, borderRadius: 4, overflow: "hidden", background: "var(--tv-bg)", marginTop: 14 }}>
        {tiers.map((t) => (
          <span key={t.key} style={{ width: `${((counts[t.key] ?? 0) / n) * 100}%`, background: TONE_COLOR[t.tone] }} />
        ))}
      </div>
    </>
  );
}

// 得分直方图：0–100 等宽 10 桶 CSS 柱状分布。posEnd=true 高分=好（绿），
// false 高分=差（红）。
export function ScoreHistogram({ scores, posEnd = true }) {
  const n = 10;
  const buckets = Array.from({ length: n }, (_, i) => ({ lo: i * 10, hi: (i + 1) * 10, count: 0 }));
  let total = 0;
  for (const s of scores || []) {
    if (!Number.isFinite(s)) continue;
    buckets[Math.min(n - 1, Math.max(0, Math.floor(s / 10)))].count++;
    total++;
  }
  const max = Math.max(1, ...buckets.map((b) => b.count));
  return (
    <div data-histogram={total}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 64, marginTop: 12 }}>
        {buckets.map((b, i) => {
          const seg = i / (n - 1);
          const tone = posEnd ? (seg >= 0.6 ? "pos" : seg >= 0.3 ? "warn" : "neg")
            : (seg >= 0.6 ? "neg" : seg >= 0.3 ? "warn" : "pos");
          return (
            <div key={i} title={`${b.lo}–${b.hi}: ${b.count} 只`} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%" }}>
              <div style={{
                height: `${(b.count / max) * 100}%`, minHeight: b.count ? 3 : 0,
                background: TONE_COLOR[tone], opacity: b.count ? 0.85 : 0.15, borderRadius: 2,
              }} />
            </div>
          );
        })}
      </div>
      <div className="muted" style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginTop: 3 }}>
        <span>0 分</span><span>{total} 只计分</span><span>100 分</span>
      </div>
    </div>
  );
}

// 可点选 chip 过滤器（信号统计/形态网格/因子桶共用）。
// items: [{key,label,tone,title,count?}]；counts: 可选 {key:n} 补充计数。
export function ChipFilter({ items, counts = {}, activeKey, onToggle, dimZero = true }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {items.map((it) => {
        // 因子桶的计数以 group:key 为键（BucketGroups 传入带 group 的 item），
        // 普通档位 chips 直接用 key；两种键都兼容。
        const cnt = (it.group != null ? counts[it.group + ":" + it.key] : undefined)
          ?? counts[it.key] ?? it.count ?? 0;
        const on = activeKey === it.key;
        return (
          <button key={it.key} type="button" data-chip={it.key} data-chip-active={on ? "1" : "0"} data-chip-count={cnt}
            title={it.title || it.label}
            onClick={() => onToggle(on ? null : it.key)}
            style={{
              padding: "3px 7px", fontSize: 11, borderRadius: 4, cursor: "pointer",
              background: on ? TONE_COLOR[it.tone] : "var(--tv-bg)",
              color: on ? "#fff" : TONE_COLOR[it.tone],
              border: `1px solid ${on ? TONE_COLOR[it.tone] : "transparent"}`,
              opacity: dimZero && cnt === 0 ? 0.4 : 1,
            }}>
            {it.label} <b style={{ fontVariantNumeric: "tabular-nums" }}>{cnt}</b>
          </button>
        );
      })}
    </div>
  );
}

// 分组版 ChipFilter（因子桶面板）。
// groups: [{group,label}]；buckets: 含 group/tone/test 的桶；counts: "group:key" → n。
export function BucketGroups({ groups, buckets, counts, active, onToggle }) {
  return (
    <>
      {groups.map((g) => (
        <div key={g.group} style={{ marginBottom: 10 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{g.label}</div>
          <ChipFilter
            items={buckets.filter((b) => b.group === g.group)}
            counts={counts}
            activeKey={active && active.group === g.group ? active.key : null}
            onToggle={(key) => onToggle(key == null ? null : { group: g.group, key })}
          />
        </div>
      ))}
    </>
  );
}

// 行内旗标明细（表格列 / 概览行）。flags: [{label,tone,title}]。
export function FlagChips({ flags, max = 5 }) {
  if (!flags || !flags.length) return <span className="muted">—</span>;
  const shown = flags.slice(0, max);
  return (
    <span style={{ display: "inline-flex", gap: 3, flexWrap: "wrap" }}>
      {shown.map((f, i) => (
        <span key={i} title={f.title || f.label}
          style={{
            fontSize: 10, padding: "1px 5px", borderRadius: 3, whiteSpace: "nowrap",
            color: TONE_COLOR[f.tone] || TONE_COLOR.neutral,
            border: `1px solid ${(TONE_COLOR[f.tone] || TONE_COLOR.neutral)}55`,
            background: "var(--tv-bg)",
          }}>
          {f.label}
        </span>
      ))}
      {flags.length > max && <span className="muted" style={{ fontSize: 10 }}>+{flags.length - max}</span>}
    </span>
  );
}
