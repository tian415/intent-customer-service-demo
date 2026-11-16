<script setup lang="ts">
import { ElAlert, ElButton, ElDialog, ElInput } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api, ApiError, errorText } from '../api/client'
import { auth } from '../state/auth'
import ServiceIcon from '../components/ServiceIcon.vue'
import SupportComposer from '../components/SupportComposer.vue'
import OrderThumbnail from '../components/OrderThumbnail.vue'
import type { ConversationDetail } from '../types'
import { formatTime, refundLabels } from '../types'
import { useBeforeUnload } from '../state/unsavedChanges'

const router = useRouter()
const route = useRoute()
const refundVisible = ref(false)
const refundReason = ref('')
const latestCase = computed(() => conversation.value?.recent_cases?.[0])
const services = [
  { label: '查物流', text: '查询这笔订单的物流', icon: 'truck' },
  { label: '申请退款', text: '我想申请退款', icon: 'refund' },
  { label: '查退款进度', text: '我的退款到哪了', icon: 'clock' },
  { label: '退款规则', text: '退款政策是什么', icon: 'policy' },
] as const
const conversation = ref<ConversationDetail | null>(null)
const draft = ref('')
const error = ref('')
const busy = ref(false)
const handoffVisible = ref(false)
const canAct = ref(true)
const log = ref<HTMLElement | null>(null)
const showOrderPicker = ref(false)
const hasUnsent = () => !!auth.user && Boolean(draft.value.trim() || (refundVisible.value && refundReason.value.trim()))
useBeforeUnload(hasUnsent)
onBeforeRouteLeave(() => !hasUnsent() || window.confirm('还有未发送的内容。离开后会丢失，确定离开吗？'))

const statusHint = computed(() => {
  const status = conversation.value?.status
  if (status === 'handed_off') return '已转人工'
  if (status === 'closed') return '已结束'
  if (status === 'waiting_order') return '请选择订单'
  return '在线'
})

const selectedOrder = computed(() => conversation.value?.selected_order ?? null)
const fresh = computed(() => !conversation.value?.messages.some(m => m.role === 'user') && !selectedOrder.value && canAct.value)

function refreshCanAct() {
  const status = conversation.value?.status
  canAct.value = status === 'active' || status === 'waiting_order'
}

watch(conversation, () => {
  refreshCanAct()
  showOrderPicker.value = conversation.value?.status === 'waiting_order'
})

watch(log, (element, _, onCleanup) => {
  if (!element) return
  let atBottom = true
  const trackPosition = () => {
    atBottom = element.scrollHeight - element.clientHeight - element.scrollTop < 24
  }
  const resize = new ResizeObserver(() => {
    if (atBottom && !fresh.value) element.scrollTop = element.scrollHeight
  })
  element.addEventListener('scroll', trackPosition)
  resize.observe(element)
  onCleanup(() => {
    element.removeEventListener('scroll', trackPosition)
    resize.disconnect()
  })
})

async function scrollBottom() {
  await nextTick()
  if (log.value) log.value.scrollTop = log.value.scrollHeight
}

async function start(forceNew = false) {
  if (busy.value) return
  if (forceNew && hasUnsent() && !window.confirm('还有未发送的内容。重新咨询会清空，确定继续吗？')) return
  busy.value = true
  error.value = ''
  try {
    conversation.value = await api<ConversationDetail>('/conversations', {
      method: 'POST',
      body: { force_new: forceNew },
    })
    if (forceNew) draft.value = ''
    await scrollBottom()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

function quickReply(text: string) {
  if (text === '转人工客服' || text === '转人工处理') openHandoff()
  else void sendText(text)
}

async function sendText(text: string) {
  if (!conversation.value || busy.value || !canAct.value) return
  const body = text.trim()
  if (!body) {
    error.value = '请输入要咨询的内容'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = await api<ConversationDetail & { show_handoff_preview: boolean }>(`/conversations/${conversation.value.id}/messages`, {
      method: 'POST',
      body: { version: conversation.value.version, body },
    })
    conversation.value = result
    if (draft.value.trim() === body) draft.value = ''
    if (result.show_handoff_preview && !draft.value.trim()) handoffVisible.value = true
    await scrollBottom()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

async function send() {
  await sendText(draft.value)
}

async function selectOrder(orderId: number) {
  if (!conversation.value || busy.value || !canAct.value) return
  if (conversation.value.selected_order_id === orderId) {
    showOrderPicker.value = false
    return
  }
  busy.value = true
  error.value = ''
  try {
    conversation.value = await api<ConversationDetail>(`/conversations/${conversation.value.id}/actions`, {
      method: 'POST',
      body: { version: conversation.value.version, action: 'select_order', order_id: orderId },
    })
    await scrollBottom()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

function openRefund() {
  const request = conversation.value?.current_request || ''
  refundReason.value = /因为|坏|故障|破损|不合适|没声音|发错/.test(request) ? request.slice(0, 1000) : ''
  refundVisible.value = true
}
function openHandoff() {
  if (!conversation.value || busy.value || !canAct.value) return
  if (draft.value.trim()) {
    error.value = '还有未发送的内容，请先发送或清空后再转人工。'
    return
  }
  if (!conversation.value.current_request) {
    error.value = '请先发送需要客服处理的问题。'
    document.getElementById('support-draft')?.focus()
    return
  }
  error.value = ''
  handoffVisible.value = true
}

async function finishChat() {
  if (!conversation.value || busy.value || !canAct.value) return
  busy.value = true
  error.value = ''
  try {
    conversation.value = await api<ConversationDetail>(`/conversations/${conversation.value.id}/actions`, {
      method: 'POST', body: { version: conversation.value.version, action: 'close' },
    })
    await scrollBottom()
  } catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}

async function confirmHandoff(refund = false) {
  if (!conversation.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    conversation.value = await api<ConversationDetail>(`/conversations/${conversation.value.id}/actions`, {
      method: 'POST',
      body: { version: conversation.value.version, action: refund ? 'submit_refund' : 'handoff', ...(refund ? {reason: refundReason.value.trim()} : {}) },
    })
    handoffVisible.value = false
    refundVisible.value = false
    refundReason.value = ''
    draft.value = ''
    await scrollBottom()
    if (conversation.value.ticket_id) await router.push(`/shop/tickets/${conversation.value.ticket_id}`)
  } catch (e) {
    handoffVisible.value = false
    refundVisible.value = false
    error.value = errorText(e)
    if (e instanceof ApiError && e.status === 409) {
      try {
        conversation.value = await api<ConversationDetail>(`/conversations/${conversation.value.id}`)
        error.value = '咨询已更新，请查看最新内容和售后进度。'
      } catch (readError) { error.value = errorText(readError) }
    }
  } finally {
    busy.value = false
  }
}

function roleLabel(role: string) {
  if (role === 'user') return '我'
  if (role === 'system') return '提示'
  if (role === 'agent') return '人工客服'
  return '售后助手'
}

onMounted(async () => {
  if (auth.user?.role !== 'user') {
    await router.replace('/staff/tickets')
    return
  }
  await start(false)
  const fromOrder = Number(route.query.order)
  if (conversation.value?.orders.some(order => order.id === fromOrder)) {
    await selectOrder(fromOrder)
    if (selectedOrder.value?.id === fromOrder) {
      const query = { ...route.query }
      delete query.order
      await router.replace({ path: route.path, query })
    }
  }
})
</script>
<template>
  <div class="support-workspace">
    <ElAlert v-if="error" class="shop-chat-alert" :title="error" type="error" show-icon :closable="false" />
    <div v-if="conversation" class="conversation-desk">
      <section class="wx-chat" aria-label="售后咨询">
        <header class="wx-bar">
          <div class="assistant-heading"><ServiceIcon name="chat" /><strong>售后助手</strong><span class="assistant-status">{{ statusHint }}</span></div>
          <div class="chat-desk-tags">
            <RouterLink v-if="conversation.ticket_id" class="ticket-pill" :to="`/shop/tickets/${conversation.ticket_id}`">售后进度<ServiceIcon name="arrow" /></RouterLink>
            <button v-if="canAct && conversation.next_action === 'answer'" type="button" class="wx-ghost-btn" :disabled="busy || !!draft.trim()" @click="finishChat"><ServiceIcon name="check" />问题已解决</button>
            <button v-if="!fresh" type="button" class="wx-ghost-btn" :disabled="busy" @click="start(true)"><ServiceIcon name="refresh" />重新咨询</button>
          </div>
        </header>
        <RouterLink v-if="fresh && latestCase" class="resume-case" :to="`/shop/tickets/${latestCase.id}`">
          <ServiceIcon name="clock" /><span>进行中的售后</span>
          <strong>{{ latestCase.product }}</strong>
          <span class="case-status">{{ latestCase.refund_stage ? refundLabels[latestCase.refund_stage] + ' · ' : '' }}{{ latestCase.status_label }}</span>
          <ServiceIcon name="arrow" />
        </RouterLink>
        <div ref="log" class="wx-log" :class="{ 'is-fresh': fresh }" aria-live="polite">
          <section v-if="fresh" class="welcome-panel" aria-labelledby="welcome-title">
            <h1 id="welcome-title">需要办理什么？</h1>
            <p>直接描述遇到的问题，或选择一项服务。</p>
            <div class="service-shortcuts" aria-label="自助办理">
              <button v-for="item in services" :key="item.label" type="button" :disabled="busy" @click="sendText(item.text)">
                <ServiceIcon :name="item.icon" /><span>{{ item.label }}</span><ServiceIcon name="arrow" />
              </button>
            </div>
          </section>
          <template v-else>
            <div
              v-for="message in conversation.messages"
              :key="message.id"
              class="wx-row"
              :data-role="message.role"
            >
              <span v-if="message.role === 'assistant' || message.role === 'agent'" class="message-symbol" aria-hidden="true">
                <ServiceIcon :name="message.role === 'agent' ? 'headset' : 'chat'" />
              </span>
              <div class="wx-bubble-wrap">
                <span v-if="message.role !== 'user' && message.role !== 'system'" class="wx-name">{{ roleLabel(message.role) }}</span>
                <article class="chat-bubble" :data-role="message.role">
                  <pre>{{ message.body }}</pre>
                </article>
                <time class="wx-time">{{ formatTime(message.created_at) }}</time>
              </div>
            </div>

            <div v-if="canAct && conversation.related_refund_id" class="service-result">
              <RouterLink :to="`/shop/tickets/${conversation.related_refund_id}`">查看退款申请 #{{ conversation.related_refund_id }} <ServiceIcon name="arrow" /></RouterLink>
            </div>
            <div v-else-if="canAct && conversation.can_submit_refund" class="service-result">
              <ElButton type="primary" :disabled="busy || !!draft.trim()" @click="openRefund">填写退款申请</ElButton>
            </div>
            <div v-if="showOrderPicker && conversation.orders.length && canAct" class="wx-order-sheet">
              <div class="picker-title">
                <p class="wx-order-sheet-title">选择相关订单</p>
                <button v-if="conversation.status !== 'waiting_order'" type="button" class="linkish" @click="showOrderPicker = false">收起</button>
              </div>
              <button
                v-for="order in conversation.orders"
                :key="order.id"
                type="button"
                class="wx-order-card"
                :data-selected="conversation.selected_order_id === order.id"
                :disabled="busy"
                @click="selectOrder(order.id)"
              >
                <OrderThumbnail :order="order" />
                <span class="wx-order-body">
                  <strong>{{ order.product_name }}</strong>
                  <span>{{ order.order_no }} · {{ order.status_label }}</span>
                </span>
                <span class="wx-order-price">{{ order.amount_display }}</span>
              </button>
            </div>

            <div v-else-if="selectedOrder && canAct" class="wx-selected-chip">
              <ServiceIcon name="box" />
              <span>已选：{{ selectedOrder.product_name }}</span>
              <button type="button" class="linkish" :disabled="busy" @click="showOrderPicker = true">更换</button>
            </div>
            <button v-else-if="canAct && conversation.orders.length" type="button" class="attach-order" :disabled="busy" @click="showOrderPicker = true">
              <ServiceIcon name="box" />关联订单
            </button>
          </template>
        </div>

        <footer class="wx-footer">
          <div v-if="!fresh && conversation.quick_replies.length && canAct" class="quick-replies wx-quick">
            <button
              v-for="item in conversation.quick_replies"
              :key="item"
              type="button"
              class="quick-reply"
              :disabled="busy"
              @click="quickReply(item)"
            >
              {{ item }}
            </button>
          </div>

          <SupportComposer v-model="draft" :busy="busy" :disabled="!canAct" @send="send" @handoff="openHandoff" />
        </footer>
      </section>
    </div>
    <p v-else-if="busy" role="status">正在打开服务中心…</p>
    <button v-else-if="error" type="button" @click="start(false)">重新加载</button>
  </div>

  <ElDialog class="support-dialog" v-model="refundVisible" title="申请退款" width="min(440px, 92vw)">
    <p>{{ selectedOrder?.product_name }} · {{ selectedOrder?.order_no }}</p>
    <label for="refund-reason">退款原因</label>
    <ElInput id="refund-reason" v-model="refundReason" type="textarea" maxlength="1000" :rows="3" placeholder="请说明商品或订单遇到的问题" />
    <p>填好原因后点「确认提交申请」才会建单。确认前可以取消。提交成功后，可在「订单与售后」查看审核进度。</p>
    <template #footer>
      <ElButton @click="refundVisible = false">取消</ElButton>
      <ElButton type="primary" :disabled="!refundReason.trim()" :loading="busy" @click="confirmHandoff(true)">确认提交申请</ElButton>
    </template>
  </ElDialog>
  <ElDialog class="support-dialog" v-model="handoffVisible" title="提交给人工客服" width="min(400px, 92vw)" :append-to-body="false">
    <p><strong>当前诉求：</strong>{{ conversation?.current_request }}</p>
    <p><strong>关联订单：</strong>{{ selectedOrder ? selectedOrder.product_name + ' · ' + selectedOrder.order_no : '未关联订单' }}</p>
    <p>提交后会建立售后单，由客服随后回复。你可以在售后详情补充说明、等待回复，也可以稍后从「订单与售后」回来查看。</p>
    <template #footer>
      <ElButton @click="handoffVisible = false">取消</ElButton>
      <ElButton type="primary" :loading="busy" @click="confirmHandoff(false)">确认提交人工</ElButton>
    </template>
  </ElDialog>
</template>
