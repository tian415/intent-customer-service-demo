<script setup lang="ts">
import { ElButton } from 'element-plus'
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, logout } from '../state/auth'
import { errorText } from '../api/client'
import ServiceIcon from '../components/ServiceIcon.vue'

import '../support-home.css'

const router = useRouter()
const route = useRoute()
const viewportHeight = ref<number>()
function updateViewportHeight() {
  viewportHeight.value = window.visualViewport?.height ?? window.innerHeight
}
onMounted(() => {
  updateViewportHeight()
  window.visualViewport?.addEventListener('resize', updateViewportHeight)
  window.addEventListener('resize', updateViewportHeight)
})
onUnmounted(() => {
  window.visualViewport?.removeEventListener('resize', updateViewportHeight)
  window.removeEventListener('resize', updateViewportHeight)
})
const busy = ref(false)
const error = ref('')

async function signOut() {
  busy.value = true
  error.value = ''
  try {
    await logout()
    await router.push('/shop/login')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="shop-shell support-home" :class="{ 'support-consulting': route.name === 'support' }" :style="{ '--consult-height': viewportHeight ? viewportHeight + 'px' : undefined }">
    <header class="shop-top">
      <RouterLink to="/shop" class="shop-brand">
        <span class="brand-mark"><ServiceIcon name="station" /></span>
        <span>
          售后驿站
        </span>
      </RouterLink>
      <nav class="shop-nav" aria-label="顾客导航">
        <RouterLink to="/shop"><ServiceIcon name="chat" />咨询客服</RouterLink>
        <RouterLink to="/shop/orders" :class="{ 'router-link-exact-active': route.path.startsWith('/shop/tickets/') }"><ServiceIcon name="orders" />订单与售后</RouterLink>
      </nav>
      <div class="shop-user">
        <span><ServiceIcon name="user" />{{ auth.user?.display_name }}</span>
        <ElButton text :loading="busy" @click="signOut" aria-label="退出"><ServiceIcon name="logout" /><span class="logout-label">退出</span></ElButton>
      </div>
    </header>
    <p v-if="error" class="shop-error">{{ error }}</p>
    <main class="shop-main">
      <RouterView />
    </main>
  </div>
</template>
