<script setup lang="ts">
import { ElAlert, ElButton, ElInput } from 'element-plus'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth, login } from '../state/auth'
import { errorText } from '../api/client'
import { homePath } from '../types'

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
    await login(username.value.trim(), password.value)
    await router.push(homePath(auth.user?.role))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <main class="login-screen">
    <section class="login-intro">
      <div class="login-atmosphere" aria-hidden="true" />
      <div class="login-grid" aria-hidden="true" />
      <span class="brand-mark login-mark">驿</span>
      <p class="login-kicker">本地电商售后演示 · 无外部大模型</p>
      <h1>先把问题说清楚，<br>再决定要不要人工。</h1>
      <p>
        智能客服识别意图、核对订单与知识库；解决不了再建售后工单，全程留痕。
        参考市面客服工作台，但全部跑在本机。
      </p>
      <ol class="login-steps">
        <li>描述问题</li>
        <li>必要时选订单</li>
        <li>知识建议或转人工</li>
      </ol>
    </section>
    <section class="login-panel">
      <p class="eyebrow">售后驿站</p>
      <h2>登录工作台</h2>
      <p class="muted">使用管理员提供的本机演示账号</p>
      <ElAlert v-if="auth.expired" title="登录已过期，请重新登录。" type="warning" :closable="false" />
      <ElAlert v-if="error" :title="error" type="error" :closable="false" role="alert" />
      <form @submit.prevent="submit">
        <label for="username">账号</label>
        <ElInput id="username" v-model="username" autocomplete="username" maxlength="40" />
        <label for="password">密码</label>
        <ElInput
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          show-password
          maxlength="128"
        />
        <ElButton class="full" type="primary" native-type="submit" :loading="busy">进入系统</ElButton>
      </form>
    </section>
  </main>
</template>
