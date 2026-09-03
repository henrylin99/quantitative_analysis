const fieldGroups = [
  {
    icon: '🪪',
    title: '身份字段',
    desc: '股票代码、名称、所属行业、地域 —— 定位一只股票是谁、在哪里。',
    fields: 'ts_code / name / industry / area',
  },
  {
    icon: '🏷️',
    title: '估值市值',
    desc: '市盈率、市净率、市销率、股息率、总市值、流通市值 —— 这只股票贵不贵、有多大。',
    fields: 'pe_ttm / pb / ps_ttm / dv_ttm / total_mv / circ_mv',
  },
  {
    icon: '📈',
    title: '当日行情',
    desc: '开高低收、涨跌幅、成交量额、换手率、量比 —— 今天交易表现如何。',
    fields: 'open / high / low / close / pct_chg / vol / amount / turnover_rate / volume_ratio',
  },
  {
    icon: '💰',
    title: '资金流向',
    desc: '主力净流入、特大/大/中/小单买卖额 —— 资金在进还是在出。',
    fields: 'net_mf_amount / buy_lg_amount / sell_lg_amount …',
  },
  {
    icon: '🔬',
    title: '技术指标',
    desc: 'MACD、KDJ、RSI、布林带、CCI、均线族 —— 经典技术分析全部算好放在表里。',
    fields: 'macd / kdj_k / rsi_6 / boll_upper / ma5 … ma120 / cci',
  },
  {
    icon: '🚀',
    title: '走强信号',
    desc: '连续上涨天数、量比放大、机构吸筹评分、20 日收益与波动 —— 量化的走强特征。',
    fields: 'consec_up_days / volume_ratio / inst_accumulation_score_10 / f_ret_20d / f_volatility_20d',
  },
  {
    icon: '🕯️',
    title: 'K 线形态',
    desc: '首板、连板、阳包阴、涨停状态等形态标签 —— 形态选股的原料。',
    fields: 'pattern_first_limit / pattern_multi_limit / pattern_bullish_engulfing / limit_status',
  },
]

const usages = [
  { icon: '🔍', title: '选股筛选', desc: '直接对上百个字段设置范围条件、字段间比较，一步筛出目标股票。' },
  { icon: '🎯', title: '形态选股', desc: '用「阳包阴 + 放量 + 首板」这样的形态标签组合，找到正在启动的股票。' },
  { icon: '🛰️', title: '其他试用功能', desc: '热力图、资金流统计、市场简报、财务健康度都基于这张表生成。' },
  { icon: '🔄', title: '数据每天更新', desc: '每个交易日收盘后自动构建最新一天的大宽表，无需自己计算。' },
]

const tips = [
  '大宽表每行是「一只股票 × 一个交易日」，只保留最新交易日，适合截面筛选而非回看历史。',
  '金额字段单位多为万元，市值字段也是万元，阅读时注意换算（10000 万 = 1 亿）。',
  '技术指标由系统按日线预先计算，字段名带 factor_ 前缀（如 factor_macd）。',
]

export default function FeatureIntroPage() {
  return (
    <div>
      <div className="hero">
        <h1>「大宽表」是什么？</h1>
        <p>
          想象一张巨大的 Excel 表格：每一行是「一只股票 × 一个交易日」，每一列是一项指标。
          全市场约 5500 只 A 股、上百项指标、每天更新 —— 这就是本系统的数据底座。
        </p>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-value">1 行</div>
          <div className="stat-label">= 一只股票 × 一天</div>
        </div>
        <div className="stat">
          <div className="stat-value">≈5500</div>
          <div className="stat-label">只 A 股</div>
        </div>
        <div className="stat">
          <div className="stat-value">100+</div>
          <div className="stat-label">项指标列</div>
        </div>
        <div className="stat">
          <div className="stat-value">每日</div>
          <div className="stat-label">收盘后更新</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            表里都有什么？
          </h6>
        </div>
        <div className="panel-body">
          <div className="tile-grid">
            {fieldGroups.map((g) => (
              <div className="tile" key={g.title}>
                <span className="icon">{g.icon}</span>
                <h3>{g.title}</h3>
                <p>{g.desc}</p>
                <code style={{ fontSize: 11.5, color: 'var(--text-faint)', wordBreak: 'break-all' }}>{g.fields}</code>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            这张表怎么帮你？
          </h6>
        </div>
        <div className="panel-body">
          <div className="tile-grid">
            {usages.map((u) => (
              <div className="tile" key={u.title}>
                <span className="icon">{u.icon}</span>
                <h3>{u.title}</h3>
                <p>{u.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h6 className="panel-title">
            <span className="kicker" />
            使用小提示
          </h6>
        </div>
        <div className="panel-body d-flex flex-column gap-2">
          {tips.map((t) => (
            <div className="alert-note" key={t}>
              💡 {t}
            </div>
          ))}
          <div className="alert-note" style={{ opacity: 0.85 }}>
            📚 更完整的字段说明见仓库文档 <code>docs/宽表数据字典.md</code>。市场有风险，投资需谨慎；本系统仅用于数据研究与学习交流。
          </div>
        </div>
      </div>
    </div>
  )
}
