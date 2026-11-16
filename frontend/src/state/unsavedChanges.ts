import { onMounted, onUnmounted } from 'vue'

export function useBeforeUnload(shouldWarn: () => boolean) {
  function warn(event: BeforeUnloadEvent) {
    if (!shouldWarn()) return
    event.preventDefault()
    event.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', warn))
  onUnmounted(() => window.removeEventListener('beforeunload', warn))
}
