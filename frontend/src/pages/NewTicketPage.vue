<script setup lang="ts">
import { ElAlert, ElButton, ElInput } from 'element-plus'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorText } from '../api/client'
import type { TicketDetail, FaqResult } from '../types'
import FaqResults from '../components/FaqResults.vue'

const router = useRouter()
const title = ref('')
const description = ref('')
const error = ref('')
const busy = ref(false)
const searching = ref(false)
const faq = ref<FaqResult | null>(null)

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!title.value.trim() || !description.value.trim()) {
    error.value = '请填写标题和问题描述'
    return
  }
  busy.value = true
  try {
    const ticket = await api<TicketDetail>('/tickets', {
      method: 'POST',
      body: { title: title.value.trim(), description: description.value.trim() },
    })
    await router.push('/tickets/' + ticket.id)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

async function recommend() {
  if (!title.value.trim() && !description.value.trim()) {
    error.value = '先填写标题或问题描述'
    return
  }
  searching.value = true
  error.value = ''
  try {
    faq.value = await api('/faq/search?q=' + encodeURIComponent((title.value + ' ' + description.value).slice(0, 1000)))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    searching.value = false
  }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>直接建单</h1>
      <p>跳过智能客服、直接创建人工售后单。日常咨询请优先走智能客服。</p>
    </div>
    <RouterLink to="/support">返回智能客服</RouterLink>
  </div>
  <ElAlert
    class="path-alert"
    type="info"
    :closable="false"
    show-icon
    title="推荐先在智能客服说明问题并选择订单；确认需要人工后再转人工，系统会自动整理工单。"
  />
  <div class="two-column">
    <section class="panel">
      <ElAlert v-if="error" :title="error" type="error" role="alert" :closable="false" />
      <form @submit.prevent="submit">
        <label for="ticket-title">问题标题</label>
        <ElInput id="ticket-title" v-model="title" maxlength="120" show-word-limit placeholder="用一句话说明问题" />
        <label for="ticket-description">问题描述</label>
        <ElInput
          id="ticket-description"
          v-model="description"
          type="textarea"
          :rows="9"
          maxlength="10000"
          show-word-limit
          placeholder="发生了什么？何时出现？已经尝试了哪些处理？"
        />
        <p class="muted">请勿填写密码、密钥或不必要的个人隐私。</p>
        <ElButton type="primary" native-type="submit" :loading="busy">提交售后单</ElButton>
      </form>
    </section>
    <aside class="panel">
      <h2>可能已有答案</h2>
      <p class="muted">知识库推荐不会代替人工处理或关闭工单。</p>
      <ElButton :loading="searching" @click="recommend">根据问题查找知识</ElButton>
      <FaqResults v-if="faq" :result="faq" />
    </aside>
  </div>
</template>
