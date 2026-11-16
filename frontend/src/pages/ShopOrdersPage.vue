<script setup lang="ts">
import { ElAlert, ElEmpty, ElPagination, vLoading } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorText } from '../api/client'
import type { Order, Ticket } from '../types'
import { formatTime, refundLabels, statusLabels } from '../types'
import OrderThumbnail from '../components/OrderThumbnail.vue'
import ServiceIcon from '../components/ServiceIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import '../service-workspace.css'

const orders = ref<Order[]>([])
const busy = ref(false)
const error = ref('')

const route = useRoute()
const router = useRouter()
const view = computed(() => route.query.view === 'orders' ? 'orders' : 'tickets')
const tickets = ref<Ticket[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)
let sequence = 0

function switchView(next: 'tickets' | 'orders') {
  if (view.value === next) return
  void router.push({ path: '/shop/orders', query: next === 'orders' ? { view: 'orders' } : {} })
}

async function load(nextPage = page.value) {
  const seq = ++sequence
  busy.value = true
  error.value = ''
  try {
    if (view.value === 'tickets') {
      const data = await api<{ items:Ticket[]; total:number }>(`/tickets?scope=mine&page=${nextPage}&page_size=${pageSize}`)
      if (seq !== sequence) return
      tickets.value = data.items
      total.value = data.total
      page.value = nextPage
    } else {
      const data = await api<Order[]>('/orders')
      if (seq === sequence) orders.value = data
    }
  } catch (e) {
    if (seq === sequence) error.value = errorText(e)
  } finally {
    if (seq === sequence) busy.value = false
  }
}

watch(view, () => { void load(1) }, { immediate: true })
</script>
<template>
  <div class="records-page">
    <header class="records-heading">
      <h1>订单与售后</h1>
      <button class="records-refresh" type="button" :disabled="busy" @click="load()"><ServiceIcon name="refresh" />刷新</button>
    </header>
    <div class="records-tabs" aria-label="记录分类">
      <button type="button" :aria-pressed="view === 'tickets'" @click="switchView('tickets')">我的全部售后</button>
      <button type="button" :aria-pressed="view === 'orders'" @click="switchView('orders')">我的订单</button>
    </div>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />

    <section v-else-if="view === 'tickets'" v-loading="busy" class="panel order-hub" aria-label="我的全部售后">
      <ElEmpty v-if="!busy && !tickets.length" description="暂无售后记录" />
      <ul v-if="tickets.length" class="aftersale-list">
        <li v-for="item in tickets" :key="item.id">
          <ServiceIcon :name="item.refund_stage ? 'refund' : 'chat'" />
          <div>
            <RouterLink :to="`/shop/tickets/${item.id}`">#{{ item.id }} {{ item.title }}</RouterLink>
            <span class="muted">{{ item.order_no || '未关联订单' }} · 更新于 {{ formatTime(item.updated_at) }}</span>
          </div>
          <StatusBadge :status="item.status" :label="item.refund_stage ? refundLabels[item.refund_stage] + ' · ' + statusLabels[item.status] : undefined" />
        </li>
      </ul>
      <ElPagination v-if="total > pageSize" layout="prev, pager, next" :total="total" :page-size="pageSize" :current-page="page" @current-change="load" />
    </section>
    <section v-else v-loading="busy" class="orders-register" aria-label="我的订单">
      <ElEmpty v-if="!busy && !orders.length" description="暂无订单" />
      <article v-for="order in orders" :key="order.id" class="purchase-record">
        <div class="purchase-summary">
          <OrderThumbnail :order="order" />
          <div class="purchase-name">
            <h2>{{ order.product_name }}</h2>
            <span>{{ order.order_no }}</span>
          </div>
          <div class="purchase-amount"><strong>{{ order.amount_display }}</strong><span>{{ order.status_label }}</span></div>
        </div>
        <div class="purchase-actions">
          <span>下单于 {{ formatTime(order.created_at) }}</span>
          <RouterLink :to="{path:'/shop', query:{order:order.id}}">咨询这笔订单<ServiceIcon name="arrow" /></RouterLink>
        </div>
        <ul v-if="order.aftersales?.length" class="aftersale-list" aria-label="售后进度">
          <li v-for="item in order.aftersales" :key="item.id">
            <div>
              <RouterLink :to="`/shop/tickets/${item.id}`">#{{ item.id }} {{ item.title }}</RouterLink>
              <span class="muted">更新于 {{ formatTime(item.updated_at) }}</span>
            </div>
            <StatusBadge :status="item.status" :label="item.status_label" />
          </li>
        </ul>
      </article>
    </section>
  </div>
</template>
<style scoped>
.records-page { max-width: 1120px; margin: 26px auto; }
.records-heading, .records-tabs, .purchase-summary, .purchase-actions { display: flex; align-items: center; gap: 14px; }
.records-heading { justify-content: space-between; }
.records-heading h1 { margin: 0; font-family: inherit; font-size: clamp(28px, 2.7vw, 36px); letter-spacing: -.06em; }
.records-refresh, .records-tabs button { border: 0; cursor: pointer; color: #57575e; background: transparent; }
.records-refresh { display: inline-flex; align-items: center; gap: 6px; min-height: 42px; font-size: 14px; }
.records-tabs { gap: 24px; margin: 14px 0 18px; border-bottom: 1px solid #d7d7db; }
.records-tabs button { border-bottom: 2px solid transparent; padding: 12px 0; font-size: 15px; }
.records-tabs button[aria-pressed=true] { border-color: #18181b; color: #18181b; font-weight: 650; }
.records-page .panel, .orders-register { background: white; border: 1px solid #dfdfe1; border-radius: 20px; box-shadow: none; }
.purchase-record { margin: 0 22px; padding: 16px 0; }
.purchase-record + .purchase-record { border-top: 1px solid #e4e4e7; }
.purchase-summary .order-thumbnail { width: 57px; height: 57px; }
.purchase-name { min-width: 0; }
.purchase-name h2 { margin: 0 0 4px; font-size: 18px; font-weight: 600; overflow-wrap: anywhere; }
.purchase-name span, .purchase-amount span, .purchase-actions > span { font-size: 13px; color: #606067; }
.purchase-amount { margin-left: auto; display: grid; gap: 3px; flex: none; text-align: right; }
.purchase-actions { justify-content: space-between; margin-top: 6px; flex-wrap: wrap; }
.purchase-actions a { display: inline-flex; gap: 6px; align-items: center; min-height: 38px; font-size: 14px; color: #27272a; }
.records-page .aftersale-list li { background: #f7f7f8; border-color: #e4e4e7; }
.purchase-record .aftersale-list { margin-top: 8px; }
@media (max-width: 600px) {
  .purchase-record { margin: 0 14px; }
  .purchase-actions { gap: 4px 10px; }
  .purchase-actions > span { font-size: 12px; }
}
</style>
