/**
 * 新手引导状态（单机单人应用，与 qa-theme 等一致存 localStorage，隐私模式下静默降级）。
 * visits 只增不清：记录用户到过哪些页面（pathname → 首次到访时间戳），
 * 任务清单据此判断「阅读教程 / 浏览行情 / 选股」等到达类任务是否完成。
 */

const STORAGE_KEY = 'qa-onboarding'

export interface OnboardingState {
  v: 1
  /** 用户手动收起清单面板 */
  dismissed: boolean
  /** pathname → 首次到访时间戳(ms) */
  visits: Record<string, number>
}

function readRaw(): OnboardingState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<OnboardingState>
      if (parsed && typeof parsed === 'object') {
        return {
          v: 1,
          dismissed: parsed.dismissed === true,
          visits: parsed.visits && typeof parsed.visits === 'object' ? parsed.visits : {},
        }
      }
    }
  } catch {
    // JSON 损坏 / localStorage 不可用：按全新状态处理
  }
  return { v: 1, dismissed: false, visits: {} }
}

function writeRaw(state: OnboardingState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // 静默降级
  }
}

export function readOnboardingState(): OnboardingState {
  return readRaw()
}

/** 记录一次页面到访（已记录过则幂等，保留首次时间戳） */
export function markRouteVisited(pathname: string) {
  if (!pathname) return
  const state = readRaw()
  if (state.visits[pathname]) return
  state.visits[pathname] = Date.now()
  writeRaw(state)
}

export function hasVisited(pathname: string): boolean {
  return Boolean(readRaw().visits[pathname])
}

export function setOnboardingDismissed(dismissed: boolean) {
  const state = readRaw()
  state.dismissed = dismissed
  writeRaw(state)
}

/**
 * 重置引导：清空到访打勾、重新展开清单，从第一步重新走一遍。
 * 只动 localStorage —— 配置/初始化/自选/AI 等服务端真实状态不受影响，
 * 重置后这几项仍按实际状态显示，避免误导用户重复配置。
 */
export function resetOnboarding() {
  writeRaw({ v: 1, dismissed: false, visits: {} })
}
