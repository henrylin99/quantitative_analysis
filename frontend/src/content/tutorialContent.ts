/**
 * 使用教程分节内容。文字改这里；截图替换同名 png 文件后重新构建即可
 * （文件在 src/assets/tutorial/，替换流程见该目录 README.md）。
 */

export interface TutorialImage {
  /** src/assets/tutorial/ 下的文件名，如 'home.png'；文件不存在时该图不渲染 */
  file: string
  caption?: string
}

export interface TutorialSection {
  id: string
  title: string
  paragraphs: string[]
  images?: TutorialImage[]
  /** 相关页面直达链接，渲染在分节末尾 */
  links?: { to: string; label: string }[]
}

export const tutorialSections: TutorialSection[] = [
  {
    id: 'welcome',
    title: '这个软件是什么',
    paragraphs: [
      '这是一个本地运行的量化研究工作台：行情浏览、选股筛选、因子研究、策略回测、AI 问数都在一个网页里完成。数据来自 Tushare 与扶摇等数据源，配置好密钥后自动下载到本机，之后所有分析都离线可用。',
      '不用会写代码 —— 左侧菜单按「概览 → 核心分析 → 数据洞察 → AI 助手」从浅到深排列，先从核心分析开始就够了，进阶功能等需要时再看。',
    ],
    images: [{ file: 'home.png', caption: '首页：任务引导、数据概况与常用功能入口' }],
    links: [
      { to: '/stocks', label: '股票列表' },
      { to: '/tutorial', label: '回到教程顶部' },
    ],
  },
  {
    id: 'quickstart',
    title: '五分钟上手路径',
    paragraphs: [
      '第一次使用按这四步走（首页的「新手引导」清单会逐步打勾提醒你）：',
      '第一步 · 配置数据源：点首页「系统配置」，填入 Tushare Token、扶摇 Key 和大模型 Key。前两个负责下载数据，大模型负责 AI 工作台，都可以免费申请（配置弹窗里有获取链接）。',
      '第二步 · 数据初始化：到数据管理页点「一键初始化」，系统会按依赖顺序自动建库、下载全市场行情与财务数据。第一次约需较长时间，之后每天增量更新很快。',
      '第三步 · 看行情、试选股：随便打开一只股票的 K 线，或者用选股筛选按估值/涨幅等条件筛一批股票。',
      '第四步 · 加自选、问 AI：把关注的股票加入自选清单，然后到 AI 工作台用一句话试试查数，比如「最近5天涨幅最大的行业是什么」。',
    ],
    images: [
      { file: 'datasources.png', caption: '数据源中心：查看各数据源的覆盖范围' },
      { file: 'data-management.png', caption: '数据管理：一键初始化与每日更新' },
    ],
    links: [
      { to: '/datasources', label: '数据源中心' },
      { to: '/data-management', label: '数据管理' },
    ],
  },
  {
    id: 'market',
    title: '看行情：股票列表与 K 线',
    paragraphs: [
      '「股票列表」是全市场行情总表：按行业、地域筛选，按涨跌幅/成交额/市值排序，点任意一行进入个股详情。',
      '「技术分析」是专业 K 线页：MACD、KDJ、RSI、布林带等指标直接叠加在图上，支持复权切换、区间缩放、十字光标读数，看盘习惯和主流行情软件一致。',
    ],
    images: [
      { file: 'stocks.png', caption: '股票列表：全市场浏览与排序' },
      { file: 'analysis.png', caption: '技术分析：专业 K 线与指标' },
    ],
    links: [
      { to: '/stocks', label: '股票列表' },
      { to: '/analysis', label: '技术分析' },
    ],
  },
  {
    id: 'screen',
    title: '选股筛选',
    paragraphs: [
      '想找「市盈率低于 20、近 5 天涨了但没涨停」的股票？选股筛选页把上百个字段做成条件卡片，自由组合、支持字段间比较，一步筛出结果。',
      '常用条件可以保存为模板，下次一键套用；结果支持导出。想按 K 线形态选股（阳包阴、首板、放量）用「形态选股」页，思路相同。',
    ],
    images: [{ file: 'screen.png', caption: '选股筛选：多条件组合' }],
    links: [
      { to: '/screen', label: '选股筛选' },
      { to: '/pattern-screen', label: '形态选股' },
    ],
  },
  {
    id: 'watchlist',
    title: '自选与每日预警',
    paragraphs: [
      '把关注的股票加入「自选行情」，每天收盘后系统自动按你设置的上下限价格检查预警（突破/跌破提醒），配合每日推送不用盯盘也能掌握动向。',
      '自选清单支持分组与备注，首页顶部也能看到自选的整体涨跌概况。',
    ],
    images: [{ file: 'watchlist.png', caption: '自选行情：分组跟踪与预警' }],
    links: [{ to: '/market/watchlist', label: '自选行情' }],
  },
  {
    id: 'market-tools',
    title: '市场工具：热力图、龙虎榜与情绪',
    paragraphs: [
      '「市场」菜单是一组盘面工具：市场看板看大盘概览，板块热力图一眼看出今天哪些行业在涨，连板天梯和涨停池判断市场情绪热度，龙虎榜看游资与机构动向。',
      '这些页面都不需要配置，数据初始化完成后直接可用。',
    ],
    images: [
      { file: 'market-dashboard.png', caption: '市场看板' },
      { file: 'limit-ladder.png', caption: '连板天梯：情绪高度' },
    ],
    links: [
      { to: '/market/dashboard', label: '市场看板' },
      { to: '/heatmap', label: '板块热力图' },
      { to: '/market/limit-up', label: '连板天梯' },
      { to: '/market/dragon-tiger', label: '龙虎榜' },
    ],
  },
  {
    id: 'ai',
    title: 'AI 工作台：用一句话查数、选股',
    paragraphs: [
      'AI 工作台接了大模型，它带着一整套查数工具：你可以直接问「贵州茅台最近一个月走势如何」「最近哪些行业主力资金在流入」「帮我筛选低估值银行股」，它会自己调接口取数、计算并给出结论，过程透明可核对。',
      '「智能查数」是它的进阶形态：把问题翻译成 SQL 直接查库，适合想要精确数字的场景。AI 回答里的表格和图表可以保存到看板，方便复查。',
    ],
    images: [
      { file: 'ai-workbench.png', caption: 'AI 工作台：对话式查数与分析' },
      { file: 'text2sql.png', caption: '智能查数：自然语言转 SQL' },
    ],
    links: [
      { to: '/ai-workbench', label: 'AI 工作台' },
      { to: '/text2sql', label: '智能查数' },
    ],
  },
  {
    id: 'insights',
    title: '数据洞察：六页深加工数据',
    paragraphs: [
      '「数据洞察」菜单把原始数据加工成六个研究视角：估值分位（这只股票现在贵不贵）、资金流深历史（主力资金长期动向）、同业对比（和同行比谁强）、组合相关性（持仓分散度）、日内统计（一天内的波动规律）、事件复盘（历史上大事发生后股价怎么走）。',
      '看个股时先翻一眼估值分位和同业对比，往往比看盘更省时间。',
    ],
    images: [{ file: 'insights-valuation.png', caption: '估值分位：历史估值百分位' }],
    links: [
      { to: '/insights/valuation', label: '估值分位' },
      { to: '/insights/moneyflow', label: '资金流深历史' },
      { to: '/insights/peer', label: '同业对比' },
      { to: '/insights/events', label: '事件复盘' },
    ],
  },
  {
    id: 'factors',
    title: '进阶：因子研究与模拟盘',
    paragraphs: [
      '「多因子模型」菜单是量化研究的核心区：因子管理查看上百个预计算因子，因子实验室可以自己组合新因子，策略管理/组合回测验证一组因子能不能赚钱，股票评分给全市场打分。这一区不需要编程，但要理解「因子 = 一种选股打分规则」。',
      '研究出想法后，可以到「模拟盘」用虚拟资金按策略自动交易，验证想法而不碰真钱。回测页提供均线/MACD/KDJ 等经典策略的快速验证。',
    ],
    images: [{ file: 'ml-factor.png', caption: '因子管理：预计算因子一览' }],
    links: [
      { to: '/ml-factor', label: '因子管理' },
      { to: '/ml-factor/factor-lab', label: '因子实验室' },
      { to: '/paper-trading', label: '模拟盘' },
    ],
  },
  {
    id: 'hk-us',
    title: '港股与美股',
    paragraphs: [
      '左侧「港股」「美股」两个菜单组覆盖港美市场：行情浏览、K 线终端、市场统计、个股风险、扫描器等页面与 A 股一一对应，操作方式完全相同，学会 A 股侧就会用。',
      '港美数据通过 yfinance 更新，在对应页面右上角点「同步」即可拉取最新数据。',
    ],
    images: [
      { file: 'hk.png', caption: '港股行情' },
      { file: 'us.png', caption: '美股行情' },
    ],
    links: [
      { to: '/hk', label: '港股行情' },
      { to: '/us', label: '美股行情' },
    ],
  },
  {
    id: 'faq',
    title: '常见问题',
    paragraphs: [
      '页面是空的、图表没数据？—— 多半是数据还没就绪：先检查首页「系统配置」三项是否全部 ✅，再到数据管理页看初始化是否完成、数据覆盖到哪一天。',
      '数据停在上一个交易日？—— 行情数据在交易日收盘后由系统自动更新（18:30 链路），也可以到数据管理页手动触发同步。',
      '界面太亮/太暗？—— 侧栏底部可以切换深浅主题。',
      '想要的新页面找不到？—— 左侧菜单就是全部功能清单，按分组浏览即可；本教程没覆盖的细节，每个页面里的字段说明和提示已经很完整。',
      '操作过一遍但没记住流程？—— 回到首页，新手引导清单右下角点「重置引导」（再点一次确认），清单即恢复到第一步重新打勾；已配置的数据源和已下载的数据不受影响。',
      '最后：本系统仅用于数据研究与学习交流，不构成任何投资建议；市场有风险，投资需谨慎。',
    ],
  },
]
