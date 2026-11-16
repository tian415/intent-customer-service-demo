<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../state/auth'
import { homePath } from '../types'

const router = useRouter()

onMounted(() => {
  if (auth.user) void router.replace(homePath(auth.user.role))
})
</script>
<template>
  <main class="portal-gate">
    <div class="portal-card">
      <span class="brand-mark">驿</span>
      <h1>售后驿站</h1>
      <p>请选择入口。顾客与员工使用不同界面，登录后按账号角色进入对应门户。</p>
      <div class="portal-actions">
        <RouterLink class="portal-btn portal-btn-shop" to="/shop/login">
          <strong>我是顾客</strong>
          <span>在线客服 · 订单与售后</span>
        </RouterLink>
        <RouterLink class="portal-btn portal-btn-staff" to="/staff/login">
          <strong>我是员工</strong>
          <span>工单处理 · 系统管理</span>
        </RouterLink>
      </div>
    </div>
  </main>
</template>
