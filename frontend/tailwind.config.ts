import type { Config } from 'tailwindcss'

/**
 * 新版设计体系（参考 tick-stock-panel 的语义 token 架构，品牌色沿用本项目靛蓝）。
 *
 * 约定：
 * - preflight 关闭：与既有 Bootstrap 页面共存，旧页面不受影响
 * - 语义色全部映射 HSL CSS 变量（见 src/styles/tsp.css），随 data-theme 自动切换
 * - 暗色不使用阴影，靠 1px 边框分层
 * - 数字一律 font-mono + tabular-nums（.num 工具类）
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        canvas: 'hsl(var(--ts-canvas) / <alpha-value>)',
        surface: 'hsl(var(--ts-surface) / <alpha-value>)',
        elevated: 'hsl(var(--ts-elevated) / <alpha-value>)',
        line: 'hsl(var(--ts-border) / <alpha-value>)',
        'fg-primary': 'hsl(var(--ts-fg-primary) / <alpha-value>)',
        'fg-secondary': 'hsl(var(--ts-fg-secondary) / <alpha-value>)',
        'fg-muted': 'hsl(var(--ts-fg-muted) / <alpha-value>)',
        accent: 'hsl(var(--ts-accent) / <alpha-value>)',
        bull: 'hsl(var(--ts-bull) / <alpha-value>)',
        bear: 'hsl(var(--ts-bear) / <alpha-value>)',
        warning: 'hsl(var(--ts-warning) / <alpha-value>)',
        danger: 'hsl(var(--ts-danger) / <alpha-value>)',
      },
      borderRadius: {
        card: '8px',
        btn: '6px',
        input: '4px',
        dialog: '12px',
      },
      fontFamily: {
        sans: [
          'Inter',
          '"HarmonyOS Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          'system-ui',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        xs: ['11px', '16px'],
        sm: ['12px', '18px'],
        base: ['13px', '20px'],
        lg: ['15px', '22px'],
      },
      transitionTimingFunction: {
        smooth: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}

export default config
