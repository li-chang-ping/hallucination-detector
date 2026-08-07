import type { TaskStatus } from './types'

export const statusText: Record<TaskStatus, string> = {
  preparing: '准备证据',
  queued: '等待中',
  running: '检测中',
  paused: '已暂停',
  completed: '已完成',
  partial: '部分完成',
  failed: '失败',
  cancelled: '已取消',
}

export function percent(value: unknown): string {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`
}

export function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}
