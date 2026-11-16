<script setup lang="ts">
import { onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { auth, clearSession } from './state/auth'
import { loginPath } from './types'
import { hasTicketDrafts } from './state/ticketWorkspace'
import { useBeforeUnload } from './state/unsavedChanges'

const router = useRouter()
useBeforeUnload(() => !!auth.user && hasTicketDrafts(auth.user.id))

function handleSessionExpired() {
  if (!auth.user) return
  const next = loginPath(auth.user.role)
  clearSession()
  auth.expired = true
  void router.push(next)
}

window.addEventListener('session-expired', handleSessionExpired)
onUnmounted(() => window.removeEventListener('session-expired', handleSessionExpired))
</script>
<template>
  <RouterView />
</template>
