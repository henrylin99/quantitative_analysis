# 使用教程截图

本目录的 png 是 `/tutorial` 使用教程页（`frontend/src/pages/TutorialPage.tsx`）引用的界面截图，
文件名被 `frontend/src/content/tutorialContent.ts` 按 `file` 字段引用。

## 更新流程

界面改版后：

1. 启动开发服务器（`scripts/dev_server.sh start`），浏览器打开对应页面；
2. 按同名文件覆盖本目录的 png（截图建议 1440×900 视口、浅色主题，与初版一致）；
3. `cd frontend && npm run build` 重新构建 —— Vite 会给图片生成新指纹 URL，浏览器不会缓存旧图；
4. 教程文字如需修改，编辑 `frontend/src/content/tutorialContent.ts`。

不需要改任何代码：`TutorialPage.tsx` 通过 `import.meta.glob` 在构建时自动发现本目录所有 png，
删除或新增文件后构建即生效（内容里引用了不存在文件时该图自然不渲染）。

## 初版截图清单

| 文件 | 对应页面 | 状态 |
|---|---|---|
| home.png | 首页 / | ✅ |
| datasources.png | 数据源中心 /datasources | ✅ |
| data-management.png | 数据管理 /data-management | ✅ |
| stocks.png | 股票列表 /stocks | ✅ |
| analysis.png | 技术分析 /analysis | ✅ |
| screen.png | 选股筛选 /screen | ✅ |
| watchlist.png | 自选行情 /market/watchlist | ✅ |
| market-dashboard.png | 市场看板 /market/dashboard | ✅ |
| limit-ladder.png | 连板天梯 /market/limit-up | ✅ |
| ai-workbench.png | AI 工作台 /ai-workbench | ✅ |
| text2sql.png | 智能查数 /text2sql | ✅ |
| insights-valuation.png | 估值分位 /insights/valuation | ✅ |
| ml-factor.png | 因子管理 /ml-factor | ✅ |
| hk.png | 港股行情 /hk | ⬜ 待本机同步港股数据后补拍（拍时页面无报错即可） |
| us.png | 美股行情 /us | ⬜ 待本机同步美股数据后补拍 |

教程页对缺失文件自动跳过（该图不渲染），所以未拍的图不影响页面；补拍时按上表文件名放入本目录并重新构建。
截图规格：1440×900 视口，浅色主题（与初版一致）。
