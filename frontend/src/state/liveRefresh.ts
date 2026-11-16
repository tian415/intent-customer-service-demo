import { onMounted, onUnmounted } from 'vue'

export function useLiveRefresh(refresh: () => Promise<void>, interval = 3000) {
  let timer: ReturnType<typeof setInterval> | undefined
  let running = false
  let active = true
  async function tick() {
    if (!active || running || document.hidden) return
    running = true
    try { await refresh() } finally { running = false }
  }
  onMounted(() => {
    timer = setInterval(() => { void tick() }, interval)
    window.addEventListener('focus', tick)
    window.addEventListener('ticket-changed', tick)
    document.addEventListener('visibilitychange', tick)
  })
  onUnmounted(() => {
    active = false
    clearInterval(timer)
    window.removeEventListener('focus', tick)
    window.removeEventListener('ticket-changed', tick)
    document.removeEventListener('visibilitychange', tick)
  })
}
