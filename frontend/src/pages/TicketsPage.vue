<script setup lang="ts">
import { ElAlert, ElButton, ElInput, ElOption, ElPagination, ElSelect, ElTable, ElTableColumn, vLoading } from 'element-plus'
import { computed, onMounted, onUnmounted, ref, toRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, errorText } from '../api/client'
import { statusLabels, formatTime } from '../types'
import ServiceIcon from '../components/ServiceIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import type { Ticket } from '../types'
import { auth } from '../state/auth'
import { queueFilters } from '../state/ticketWorkspace'
import { useLiveRefresh } from '../state/liveRefresh'
import { getSessionRevision } from '../api/client'

const items = ref<Ticket[]>([])
const total = ref(0)
const page = toRef(queueFilters, 'page')
const query = toRef(queueFilters, 'query')
const status = toRef(queueFilters, 'status')
const scope = toRef(queueFilters, 'scope')
const route = useRoute()
const scopes = computed(() => [{key:'todo',label:auth.user?.role === 'admin' ? '全部待处理' : '我的待处理'},{key:'queue',label:'待接单队列'},{key:'waiting',label:'待顾客反馈'},{key:'done',label:'已完成'},{key:'all',label:'可见全部'}])
const busy = ref(false)
const error = ref('')
let requestId = 0
onUnmounted(() => { ++requestId })

async function load(reset = false, silent = false) {
  if (silent && busy.value) return
  if (reset) page.value = 1
  const id = ++requestId
  if (!silent) { busy.value = true; error.value = '' }
  const session = getSessionRevision()
  try {
    const data = await api<{ items: Ticket[]; total: number }>('/tickets?' + new URLSearchParams({
      q: query.value,
      status: status.value,
      scope: scope.value,
      page: String(page.value),
      page_size: '20',
    }))
    if (id === requestId && session === getSessionRevision()) {
      items.value = data.items
      total.value = data.total
      error.value = ''
    }
  } catch (e) {
    if (id === requestId) error.value = errorText(e)
  } finally {
    if (id === requestId) busy.value = false
  }
}

function setScope(next: string) {
  scope.value = next
  void load(true)
}

function applyRouteFilters() {
  const requested = route.query.scope
  if (typeof requested === 'string' && scopes.value.some(s => s.key === requested)) {
    scope.value = requested
    query.value = ''
    status.value = typeof route.query.status === 'string' && route.query.status in statusLabels ? route.query.status : ''
    page.value = 1
  }
  void load()
}
onMounted(applyRouteFilters)
watch(() => route.query, applyRouteFilters)
useLiveRefresh(() => load(false, true))
</script>
<template>
  <div class="ticket-list-page">
  <header class="page-heading">
    <h1>工单台</h1>
    <span class="queue-total">{{ total }} 张工单</span>
  </header>

  <section class="panel path-hint staff-scope-bar">
    <div class="scope-chips">
      <button v-for="item in scopes" :key="item.key" type="button" class="scope-chip" :data-active="scope === item.key" @click="setScope(item.key)">{{ item.label }}</button>
    </div>
  </section>

  <section class="panel dense-panel table-panel">
    <form class="toolbar" @submit.prevent="load(true)">
      <ElInput v-model="query" placeholder="搜索标题或描述" aria-label="搜索工单" maxlength="120" clearable><template #prefix><ServiceIcon name="search" /></template></ElInput>
      <ElSelect v-model="status" placeholder="全部状态" aria-label="工单状态" clearable>
        <ElOption v-for="(label, key) in statusLabels" :key="key" :label="label" :value="key" />
      </ElSelect>
      <ElButton native-type="submit" :loading="busy">查询</ElButton>
    </form>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <div v-loading="busy" class="table-scroll">
      <ElTable :data="items" :empty-text="query || status ? '没有符合当前筛选条件的工单' : scope === 'todo' ? '当前没有待处理工单' : '当前队列暂无工单'" style="width: 100%" size="small">
        <ElTableColumn label="问题" min-width="240">
          <template #default="{ row }">
            <RouterLink :to="'/staff/tickets/' + row.id" class="ticket-link">#{{ row.id }} {{ row.title }}</RouterLink>
            <div class="muted">{{ row.owner_name }}<template v-if="row.order_no"> · {{ row.order_no }}</template></div>
            <div v-if="row.needs_staff_reply" class="reply-needed">顾客有补充 · 待回复</div>
            <div v-if="row.latest_public_reply" class="message-preview">{{ row.latest_public_reply.from_customer ? '顾客：' : '客服：' }}{{ row.latest_public_reply.body }}</div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" min-width="100">
          <template #default="{ row }">
            <StatusBadge :status="row.status" />
          </template>
        </ElTableColumn>
        <ElTableColumn prop="category_name" label="分类" min-width="100">
          <template #default="{ row }">{{ row.category_name || '待分类' }}</template>
        </ElTableColumn>
        <ElTableColumn label="承办" min-width="100">
          <template #default="{ row }">{{ row.assignee_name || '待分配' }}</template>
        </ElTableColumn>
        <ElTableColumn label="更新" min-width="160">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </ElTableColumn>
      </ElTable>
    </div>
    <ElButton v-if="!busy && !error && !items.length && !query && !status && scope === 'todo'" text type="primary" @click="setScope('queue')">查看待接单队列</ElButton>
    <ElPagination v-if="total > 20"
      v-model:current-page="page"
      :page-size="20"
      :total="total"
      layout="prev, pager, next"
      @current-change="load()"
    />
  </section>
  </div>
</template>
