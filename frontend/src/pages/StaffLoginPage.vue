<script setup lang="ts">
import { ElAlert, ElButton, ElInput } from 'element-plus'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth, login } from '../state/auth'
import { errorText } from '../api/client'
import { homePath } from '../types'
import ServiceIcon from '../components/ServiceIcon.vue'
import '../support-home.css'
import '../service-workspace.css'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  busy.value = true
  try {
    await login(username.value.trim(), password.value, 'staff')
    await router.push(homePath(auth.user?.role))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <main class="service-auth support-home">
    <section class="service-auth-panel">
      <div class="auth-brand"><ServiceIcon name="station" />售后驿站</div>
      <h1>工单工作台</h1>
      <p class="muted">登录后接单、回复顾客和跟进处理结果。</p>
      <ElAlert v-if="auth.expired" title="登录已过期，请重新登录。" type="warning" :closable="false" />
      <ElAlert v-if="error" :title="error" type="error" :closable="false" role="alert" />
      <form @submit.prevent="submit">
        <label for="staff-username">账号</label>
        <ElInput id="staff-username" v-model="username" autocomplete="username" maxlength="40" />
        <label for="staff-password">密码</label>
        <ElInput id="staff-password" v-model="password" type="password" autocomplete="current-password" show-password maxlength="128" />
        <ElButton class="full" type="primary" native-type="submit" :loading="busy">进入工作台</ElButton>
      </form>
      <p class="muted login-switch">顾客请走 <RouterLink to="/shop/login">顾客入口</RouterLink></p>
    </section>
  </main>
</template>
