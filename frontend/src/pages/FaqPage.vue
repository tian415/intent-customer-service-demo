<script setup lang="ts">
import { ElAlert, ElButton, ElEmpty, ElInput } from 'element-plus'
import { ref } from 'vue'
import { auth } from '../state/auth'
import { api, errorText } from '../api/client'
import type { FaqResult } from '../types'
import FaqResults from '../components/FaqResults.vue'

const query = ref('')
const result = ref<FaqResult | null>(null)
const error = ref('')
const busy = ref(false)

async function search() {
  if (busy.value) return
  if (!query.value.trim()) {
    error.value = '请输入问题或关键词'
    return
  }
  busy.value = true
  error.value = ''
  try {
    result.value = await api('/faq/search?q=' + encodeURIComponent(query.value))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">自助服务</p>
      <h1>知识库</h1>
      <p>先查找已有解答；不够用再走智能客服或创建工单。知识命中不会伪装成人工结单。</p>
    </div>
    <RouterLink v-if="auth.user?.role === 'user'" to="/support">
      <ElButton type="primary">去智能客服</ElButton>
    </RouterLink>
  </div>
  <section class="panel">
    <form class="toolbar" @submit.prevent="search">
      <ElInput v-model="query" placeholder="输入问题或关键词" aria-label="知识库搜索" maxlength="1000" />
      <ElButton type="primary" native-type="submit" :loading="busy">搜索知识</ElButton>
    </form>
    <ElAlert v-if="error" :title="error" type="error" />
    <FaqResults v-if="result" :result="result" />
    <ElEmpty v-else description="输入关键词搜索本地知识库" />
  </section>
</template>
