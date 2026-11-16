<script setup lang="ts">
import { ElButton } from 'element-plus'
import { ref, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, logout } from '../state/auth'
import { api, errorText } from '../api/client'
import type { Ticket } from '../types'
import ServiceIcon from '../components/ServiceIcon.vue'
import '../support-home.css'
import '../service-workspace.css'
import { roleLabels } from '../types'
import { useLiveRefresh } from '../state/liveRefresh'
import { getSessionRevision } from '../api/client'

const router = useRouter()
const busy = ref(false)
const error = ref('')

const route = useRoute()
const nearby = ref<Ticket[]>([])
const queueError = ref('')
let requestId = 0
onUnmounted(() => { ++requestId })
async function loadQueue() {
  if (!route.params.id) return
  const id = ++requestId
  const session = getSessionRevision()
  try {
    const page = await api<{items:Ticket[]}>('/tickets?scope=todo&page=1&page_size=6')
    if (id === requestId && session === getSessionRevision()) { nearby.value = page.items; queueError.value = '' }
  } catch (e) { if (id === requestId) queueError.value = errorText(e) }
}
watch(() => route.params.id, () => { ++requestId; void loadQueue() }, {immediate:true})
useLiveRefresh(loadQueue)

async function signOut() {
  busy.value = true
  error.value = ''
  try {
    await logout()
    await router.push('/staff/login')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="staff-shell">
    <aside class="staff-sidebar">
      <RouterLink to="/staff/tickets" class="brand staff-brand">
        <span class="brand-mark"><ServiceIcon name="station" /></span>
        <span>售后驿站<small class="brand-sub">客服工作台</small></span>
      </RouterLink>
      <nav aria-label="员工导航">
        <RouterLink to="/staff/tickets" :class="{ 'router-link-active': route.path.startsWith('/staff/tickets/') }"><ServiceIcon name="inbox" />工单台</RouterLink>
        <RouterLink v-if="auth.user?.role === 'admin'" to="/staff/admin" :class="{ 'router-link-active': route.path.startsWith('/staff/admin') }"><ServiceIcon name="settings" />系统管理</RouterLink>
      </nav>
      <section v-if="route.params.id" class="nearby-cases" :aria-label="auth.user?.role === 'admin' ? '全部待处理' : '我的待处理'">
        <h2>{{ auth.user?.role === 'admin' ? '全部待处理' : '我的待处理' }}</h2>
        <RouterLink v-for="item in nearby" :key="item.id" :to="`/staff/tickets/${item.id}`">
          <small>#{{ item.id }} · {{ item.owner_name }}</small>{{ item.title }}
          <span v-if="item.needs_staff_reply" class="needs-reply">顾客有补充 · 待回复</span>
        </RouterLink>
        <p v-if="!nearby.length" class="muted">暂无待处理工单</p>
        <RouterLink class="back-to-queue" :to="{path:'/staff/tickets',query:{scope:'queue'}}">查看待接单队列</RouterLink>
        <span v-if="queueError">{{ queueError }}</span>
      </section>
    </aside>
    <section class="workspace">
      <header class="topbar staff-topbar">
        <span>{{ route.params.id ? '工单处理 / #' + route.params.id : route.path.includes('/admin') ? '系统管理' : '工单处理' }}</span>
        <div>
          <ServiceIcon name="user" /><span>{{ auth.user?.display_name }}</span>
          <small>{{ auth.user ? roleLabels[auth.user.role] : '' }}</small>
          <ElButton text :loading="busy" @click="signOut"><ServiceIcon name="logout" />退出</ElButton>
        </div>
      </header>
      <p v-if="error" class="shop-error">{{ error }}</p>
      <main class="content staff-content"><RouterView /></main>
    </section>
  </div>
</template>
