import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** 合并 className（条件类 + tailwind 类冲突消解） */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
