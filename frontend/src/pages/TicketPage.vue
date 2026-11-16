<script setup lang="ts">
import { ElAlert, ElButton, ElEmpty, ElInput, ElOption, ElSelect, ElTag, vLoading } from 'element-plus'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiError, errorText, getSessionRevision } from '../api/client'
import { auth } from '../state/auth'
import { ticketPermissions } from '../state/tickets'
import { refundLabels, formatTime, predictionSourceLabels } from '../types'
import type { TicketDetail, Catalog, FaqResult } from '../types'
import FaqResults from '../components/FaqResults.vue'
import ServiceIcon from '../components/ServiceIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import '../service-workspace.css'
import { ticketDraft, announceTicketChange } from '../state/ticketWorkspace'
import { useLiveRefresh } from '../state/liveRefresh'

const route = useRoute()
const router = useRouter()
const listPath = computed(() => (route.path.startsWith('/shop') ? '/shop/orders' : '/staff/tickets'))
const listLabel = computed(() => (route.path.startsWith('/shop') ? '返回订单与售后' : '返回工单台'))
const isShop = computed(() => route.path.startsWith('/shop'))
const ticket = ref<TicketDetail | null>(null)
const catalog = ref<Catalog>({ categories: [], groups: [], agents: [] })
const error = ref('')
const busy = ref(false)
const loading = ref(false)
const conflict = ref(false)
const draft = computed(() => ticketDraft(auth.user?.id ?? 0, String(route.params.id)))
const continuing = ref(false)
const internal = computed(() => draft.value.mode === 'internal')
const resolving = computed(() => draft.value.mode === 'resolve')
const body = computed({
  get: () => continuing.value ? draft.value.followupText : resolving.value ? draft.value.decisionText : internal.value ? draft.value.privateText : draft.value.publicText,
  set: value => { if (continuing.value) draft.value.followupText = value; else if (resolving.value) { if (!draft.value.decisionText) draft.value.reviewVersion = ticket.value?.version ?? null; draft.value.decisionText = value } else if (internal.value) draft.value.privateText = value; else draft.value.publicText = value },
})
const refundDecision = computed({get: () => draft.value.refundDecision, set: value => { draft.value.refundDecision = value }})
function setAudience(isPrivate: boolean) {
  draft.value.mode = isPrivate ? 'internal' : 'reply'
}
const assignee = ref<number>()
const category = ref<number>()
const reason = ref('')
const transferReason = ref('')
const faq = ref<FaqResult | null>(null)
const faqError = ref('')

const permissions = computed(() => (ticket.value && auth.user ? ticketPermissions(ticket.value, auth.user) : null))
const targetCategory = computed(() => catalog.value.categories.find((c) => c.id === ticket.value?.category_id))
const agents = computed(() =>
  catalog.value.agents.filter(
    (a) => a.active && (targetCategory.value?.group_id == null || a.group_id === targetCategory.value.group_id),
  ),
)
const milestones = computed(() => (ticket.value?.events || []).flatMap(event => {
  if (event.kind === 'created') return [{...event, label:'申请已登记'}]
  if (event.kind === 'refund_review') return [{...event, label:event.detail}]
  if (event.kind !== 'status') return []
  const labels:Record<string,string> = {accept:'客服已接单', close:'顾客已确认结束服务', reopen:'顾客请求重新核查', follow_up:'顾客反馈仍需帮助'}
  const label = labels[event.detail.split(':')[0] || '']
  return label ? [{...event,label}] : []
}).reverse())
const myName = computed(() => auth.user?.display_name || '')
function isMineMessage(authorName: string) {
  return Boolean(myName.value) && authorName === myName.value
}
function messageKind(authorName: string, internalNote: boolean) {
  if (internalNote) return 'system'
  if (isMineMessage(authorName)) return 'user'
  return 'agent'
}
const messagesLog = ref<HTMLElement | null>(null)
const syncError = ref('')
const updateNotice = ref('')
const nextBusy = ref(false)
const reviewNeedsCheck = ref(false)
const latestStaffReply = computed(() => ticket.value?.messages.slice().reverse().find(m => !m.internal && (m.author_id !== undefined ? m.author_id !== ticket.value?.owner_id : m.author_name !== ticket.value?.owner_name)))
const requestBrief = computed(() => {
  const description = ticket.value?.description || ''
  return description.startsWith('来自智能客服') ? ticket.value?.title : description.split('\n来自智能客服')[0]
})
const syncLabel = computed(() => syncError.value || '回复与进度自动更新')

async function showLatest() {
  await nextTick()
  if (messagesLog.value) messagesLog.value.scrollTop = messagesLog.value.scrollHeight
  if (isShop.value) document.querySelector('.conversation-panel')?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  updateNotice.value = ''
}
async function continueHelp() {
  continuing.value = true
  await showLatest()
  document.getElementById('reply')?.focus()
}

let loadId = 0
let mutationId = 0
let faqId = 0
let disposed = false
onUnmounted(() => { disposed = true; ++loadId; ++mutationId })

async function load(silent = false) {
  if (silent && (busy.value || loading.value || conflict.value || !ticket.value)) return
  const id = ++loadId
  const ticketId = String(route.params.id)
  const session = getSessionRevision()
  if (!silent) { loading.value = true; error.value = '' }
  try {
    const result = await api<TicketDetail>('/tickets/' + ticketId)
    if (id === loadId && !disposed && session === getSessionRevision()) {
      const previous = ticket.value
      if (silent && previous && result.version <= previous.version) { syncError.value = ''; return }
      const lastId = previous?.messages.at(-1)?.id ?? 0
      const incoming = result.messages.filter(m => m.id > lastId && !m.internal && (m.author_id !== undefined ? m.author_id !== auth.user?.id : m.author_name !== auth.user?.display_name))
      const log = messagesLog.value
      const atBottom = !log || log.scrollHeight - log.scrollTop - log.clientHeight < 40
      ticket.value = result
      if (draft.value.decisionText && draft.value.reviewVersion !== null && draft.value.reviewVersion !== result.version) reviewNeedsCheck.value = true
      conflict.value = false
      syncError.value = ''
      if (silent && previous) {
        if (incoming.length) updateNotice.value = isShop.value ? '收到客服的新回复' : '顾客发来了新消息'
        else if (result.status !== previous.status) updateNotice.value = '处理进度已更新'
        if (incoming.length && (draft.value.decisionText || draft.value.refundDecision)) reviewNeedsCheck.value = true
      }
      await nextTick()
      if (atBottom && messagesLog.value) messagesLog.value.scrollTop = messagesLog.value.scrollHeight
    }
  } catch (e) {
    if (id === loadId && !disposed && session === getSessionRevision()) {
      if (silent) syncError.value = '自动更新暂不可用，请检查连接或点击刷新。'
      else error.value = errorText(e)
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        ticket.value = null
        error.value = errorText(e) + '。请返回工单列表查看可访问的工单。'
      }
    }
  } finally {
    if (id === loadId) loading.value = false
  }
}
useLiveRefresh(() => load(true))

async function mutate(action: string) {
  if (!ticket.value || busy.value || loading.value || conflict.value) return
  if (action === 'resolve' && reviewNeedsCheck.value) return
  error.value = ''
  if (['message', 'resolve', 'follow_up'].includes(action) && !body.value.trim()) {
    error.value = '请填写要发送的内容'
    return
  }
  if (action === 'transfer' && (!assignee.value || !transferReason.value.trim())) {
    error.value = '请选择目标客服并填写转派理由'
    return
  }
  if (action === 'classify' && (!category.value || !reason.value.trim())) {
    error.value = '请选择分类并填写纠错理由'
    return
  }
  const id = ++mutationId
  ++loadId // An older polling response must not replace this mutation result.
  const session = getSessionRevision()
  const ticketId = ticket.value.id
  const sendingDraft = draft.value
  const field = action === 'follow_up' ? 'followupText' : action === 'resolve' ? 'decisionText' : internal.value ? 'privateText' : 'publicText'
  const sentText = sendingDraft[field]
  const data =
    action === 'message'
      ? { version: ticket.value.version, body: body.value.trim(), internal: permissions.value?.staff && internal.value }
      : {
          version: ticket.value.version,
          action,
          ...(['resolve', 'follow_up'].includes(action) ? { reason: body.value.trim() } : {}),
          ...(action === 'resolve' && ticket.value.refund_stage ? { refund_decision: refundDecision.value } : {}),
          ...(action === 'transfer' ? { assignee_id: assignee.value, reason: transferReason.value.trim() } : {}),
          ...(action === 'classify' ? { category_id: category.value, reason: reason.value.trim() } : {}),
        }
  busy.value = true
  try {
    const result = await api<TicketDetail>('/tickets/' + ticketId + (action === 'message' ? '/messages' : '/actions'), {
      method: 'POST',
      body: data,
    })
    // Complete the original draft even if its tab was left while sending.
    // Never remove text typed after the request, or touch another session.
    if (session !== getSessionRevision()) return
    if (['message', 'resolve', 'follow_up'].includes(action) && sendingDraft[field] === sentText) sendingDraft[field] = ''
    if (action === 'resolve') { sendingDraft.refundDecision = ''; sendingDraft.reviewVersion = null; sendingDraft.mode = 'reply' }
    announceTicketChange()
    if (id !== mutationId || disposed) return
    ticket.value = result
    if (action === 'follow_up') continuing.value = false
    updateNotice.value = action === 'follow_up' ? '补充已发送，客服将继续处理这张售后单。' : ''
    if (action === 'classify') reason.value = ''
    if (action === 'transfer') transferReason.value = ''
    await nextTick()
    if (messagesLog.value) messagesLog.value.scrollTop = messagesLog.value.scrollHeight
  } catch (e) {
    if (id === mutationId && !disposed && session === getSessionRevision()) {
      error.value = errorText(e)
      if (e instanceof ApiError && e.status === 409) conflict.value = true
    }
  } finally {
    if (id === mutationId) busy.value = false
  }
}

async function nextTicket() {
  nextBusy.value = true
  try {
    const page = await api<{items:TicketDetail[]}>('/tickets?scope=todo&page_size=20')
    const next = page.items.find(t => t.id !== ticket.value?.id)
    await router.push(next ? '/staff/tickets/' + next.id : '/staff/tickets')
  } catch (e) { error.value = errorText(e) }
  finally { nextBusy.value = false }
}

async function recommend() {
  if (!ticket.value) return
  const id = ++faqId
  const title = ticket.value.title
  faqError.value = ''
  try {
    const result = await api<FaqResult>('/faq/search?q=' + encodeURIComponent(title))
    if (id === faqId) faq.value = result
  } catch (e) {
    if (id === faqId) faqError.value = errorText(e)
  }
}

onMounted(async () => {
  try {
    catalog.value = await api('/catalog')
  } catch (e) {
    error.value = errorText(e)
  }
})

watch(
  () => route.params.id,
  () => {
    ++mutationId
    ++faqId
    ticket.value = null
    continuing.value = !!draft.value.followupText
    reviewNeedsCheck.value = false
    updateNotice.value = ''
    syncError.value = ''
    assignee.value = undefined
    category.value = undefined
    reason.value = ''
    transferReason.value = ''
    faq.value = null
    faqError.value = ''
    conflict.value = false
    busy.value = false
    void load(false)
  },
  { immediate: true },
)
</script>
<template>
  <div class="ticket-page" :class="isShop ? 'customer-ticket' : 'staff-ticket'">
  <div class="page-heading">
    <div>
      <RouterLink class="back-link" :to="listPath"><ServiceIcon name="back" />{{ listLabel }}</RouterLink>
      <h1>{{ isShop ? '售后进度' : '工单' }} #{{ route.params.id }}</h1>
    </div>
    <div class="detail-tools"><span class="muted sync-status" role="status">{{ syncLabel }}</span><ElButton :loading="loading" :disabled="busy" @click="load(false)"><ServiceIcon name="refresh" />刷新</ElButton></div>
  </div>

  <ElAlert v-if="error" :title="error" type="error" :closable="false" />
  <div v-if="updateNotice && !(!isShop && resolving && reviewNeedsCheck)" class="reply-notice" role="status"><span>{{ updateNotice }}</span><button type="button" @click="showLatest">查看最新消息</button></div>
  <ElAlert
    v-if="conflict"
    title="其他人已更新此工单。请刷新后核对状态再提交，当前输入已保留。"
    type="warning"
    :closable="false"
  />

  <div v-loading="loading" class="ticket-content">
    <div v-if="ticket && permissions" class="ticket-desk" :class="{'customer-case':isShop}">
      <section class="ticket-main">
        <article class="panel ticket-hero">
          <div class="title-row">
            <div>
              <p class="eyebrow">{{ ticket.product_name || (isShop ? '我的售后' : '售后处理') }}</p>
              <h2>{{ isShop && ticket.refund_stage ? refundLabels[ticket.refund_stage] : ticket.title }}</h2>
            </div>
            <StatusBadge :status="ticket.status" />
          </div>
          <template v-if="isShop">
            <p class="case-guidance">{{ ticket.status === 'closed' ? '本次服务已结束。仍需帮助时，可以补充问题继续跟进。' : ticket.status === 'resolved' ? '客服已提供处理意见。请核对结果，仍有问题可继续反馈。' : '等待客服回复。你可以留在此页，或稍后从「订单与售后」回来查看。' }}</p>
            <div v-if="latestStaffReply" class="latest-response"><strong>客服最新回复</strong><p class="prose">{{ latestStaffReply.body }}</p></div>
            <p v-if="ticket.refund_stage === 'approved'" class="refund-boundary">本系统记录退款审核意见，尚无实际到账凭证。</p>
          </template>
          <p v-else-if="requestBrief !== ticket.title" class="request-brief prose">{{ requestBrief }}</p>
          <details v-if="isShop"><summary>申请内容</summary><p class="prose">{{ ticket.description }}</p></details>
          <details v-if="!isShop && ticket.customer_statements?.length">
            <summary>查看顾客原话（{{ ticket.customer_statements.length }} 条）</summary>
            <ol><li v-for="(line, index) in ticket.customer_statements" :key="index" class="prose">{{ line }}</li></ol>
          </details>
          <div v-if="isShop" class="metadata">
            <span v-if="isShop && ticket.order_no">订单 {{ ticket.order_no }}{{ ticket.product_name ? ` · ${ticket.product_name}` : '' }}</span>
            <span>创建于 {{ formatTime(ticket.created_at) }}</span>
            <span v-if="isShop">更新于 {{ formatTime(ticket.updated_at) }}</span>
          </div>
          <div class="actions">
            <ElButton v-if="permissions.accept" type="primary" :loading="busy" :disabled="conflict" @click="mutate('accept')">
              接单并开始处理
            </ElButton>
            <ElButton v-if="permissions.reopen" type="primary" :disabled="busy || conflict" @click="continueHelp">
              {{ ticket.status === 'resolved' ? '问题还没解决' : '仍需帮助' }}
            </ElButton>
            <ElButton v-if="permissions.close" :loading="busy" :disabled="conflict" @click="mutate('close')">
              确认结束本次服务
            </ElButton>
            <ElButton v-if="!isShop && ['resolved','closed'].includes(ticket.status)" :loading="nextBusy" @click="nextTicket">下一张待处理<ServiceIcon name="arrow" /></ElButton>
          </div>
        </article>

        <section class="panel conversation-panel">
          <h2>沟通记录</h2>
          <div ref="messagesLog" class="ticket-message-log">
          <p v-if="!ticket.messages.length" class="conversation-empty">{{ isShop ? '客服尚未回复。有新的说明可以直接补充。' : '还没有沟通记录，先核对申请内容，再回复顾客。' }}</p>
          <div
            v-for="message in ticket.messages"
            :key="message.id"
            class="wx-row ticket-msg-row"
            :data-role="isShop ? messageKind(message.author_name, message.internal) : 'agent'"
            :class="{ internal: message.internal }"
          >
            <span
              v-if="isShop && !message.internal"
              class="message-person"
              :data-kind="messageKind(message.author_name, false)"
              aria-hidden="true"
            >
              <ServiceIcon :name="isMineMessage(message.author_name) ? 'user' : 'headset'" />
            </span>
            <article class="message" :class="{ internal: message.internal, 'chat-bubble': isShop && !message.internal }" :data-role="messageKind(message.author_name, message.internal)">
              <div class="metadata">
                <strong>{{ isShop && isMineMessage(message.author_name) ? '我' : message.author_name }}</strong>
                <ElTag v-if="message.internal" type="warning" size="small">内部备注</ElTag>
                <span>{{ formatTime(message.created_at) }}</span>
              </div>
              <p class="prose">{{ message.body }}</p>
            </article>
          </div>
          </div>
          <form v-if="permissions.reply || (continuing && permissions.reopen)" class="reply-form" @submit.prevent="mutate(continuing ? 'follow_up' : resolving ? 'resolve' : 'message')">
            <div v-if="permissions.staff" class="audience-switch">
              <button type="button" :aria-pressed="!internal && !resolving" @click="setAudience(false)">回复顾客</button>
              <button type="button" :aria-pressed="internal" @click="setAudience(true)">写内部备注</button>
              <button v-if="permissions.resolve" type="button" :aria-pressed="resolving" @click="draft.mode = 'resolve'">提交处理结果</button>
            </div>
            <div class="editor-fields">
            <div v-if="resolving && permissions.resolve && ticket.refund_stage" class="decision-choice">
              <label for="refund-decision">审核结论</label>
              <select id="refund-decision" v-model="refundDecision" required><option value="" disabled>请选择</option><option value="approved">审核通过</option><option value="declined">未通过审核</option></select>
            </div>
            <p v-if="continuing" class="muted editor-hint">补充内容会交给客服继续处理，保留原有沟通记录。</p>
            <div v-if="resolving && reviewNeedsCheck" class="review-update" role="alert">工单有更新，请核对最新消息后提交。<button type="button" @click="reviewNeedsCheck = false; draft.reviewVersion = ticket.version; updateNotice = ''">已核对最新内容</button></div>
            <label for="reply">{{ continuing ? '仍需帮助的问题' : resolving ? '给顾客的处理意见' : internal && permissions.staff ? '内部备注' : '公开回复' }}</label>
            <ElInput id="reply" v-model="body" type="textarea" :rows="resolving ? 2 : 3" :maxlength="resolving || continuing ? 1000 : 10000" show-word-limit :disabled="busy" />
            </div>
            <div class="actions">
              <span class="muted draft-hint">{{ internal ? '仅工作人员可见 · ' : resolving ? '处理意见公开发送 · ' : '' }}切单保留草稿，刷新或退出会清除</span>
              <ElButton type="primary" native-type="submit" :loading="busy" :disabled="conflict || (resolving && (!permissions.resolve || reviewNeedsCheck || (!!ticket.refund_stage && !refundDecision)))">
                {{ continuing ? '发送并继续处理' : resolving ? '发送处理结果' : internal && permissions.staff ? '保存内部备注' : '发送回复' }}
              </ElButton>
            </div>
          </form>
          <p v-else class="muted">
            {{
              ticket.status === 'resolved' || ticket.status === 'closed'
                ? (isShop ? '仍需帮助时，点击上方按钮补充问题。' : '处理意见已发出，等待顾客反馈。')
                : (permissions.accept ? '接单后即可回复顾客。' : `此单由 ${ticket.assignee_name || '其他客服'} 跟进。请从我的待处理选择可操作的工单。`)
            }}
          </p>
        </section>

      </section>

      <aside class="ticket-side">
        <section v-if="!isShop" class="panel properties-panel">
          <h2>关联信息</h2>
          <p>提交人 · {{ ticket.owner_name }}<br><small>创建于 {{ formatTime(ticket.created_at) }}</small></p>
          <p>{{ ticket.product_name || '未关联订单' }}<br><small>{{ ticket.order_no }}</small></p>
          <dl v-if="ticket.order" class="order-facts"><dt>订单金额</dt><dd>{{ ticket.order.amount_display }}</dd><dt>订单状态</dt><dd>{{ ticket.order.status_label }}</dd><dt>购买时间</dt><dd>{{ formatTime(ticket.order.created_at) }}</dd></dl>
          <p>承办客服 · {{ ticket.assignee_name || '待分配' }}</p>
          <details><summary>分类与识别依据</summary>

          <dl>
            <dt>分类</dt>
            <dd>{{ ticket.category_name || '待分类' }}</dd>
            <dt>承办客服</dt>
            <dd>{{ ticket.assignee_name || '待分配' }}</dd>
            <dt>分类来源</dt>
            <dd>{{ predictionSourceLabels[ticket.prediction_source] || ticket.prediction_source }}</dd>
            <dt>{{ ticket.prediction_source === 'model' ? '模型分值（未经校准）' : '匹配分值（非概率）' }}</dt>
            <dd>{{ ticket.prediction_score ?? '无' }}</dd>
            <template v-if="ticket.prediction_model_version">
              <dt>模型文件版本</dt>
              <dd :title="ticket.prediction_model_version">{{ ticket.prediction_model_version.slice(0, 12) }}</dd>
            </template>
            <template v-if="permissions.staff && ticket.prediction_label">
              <dt>原模型标签</dt>
              <dd>{{ ticket.prediction_label }}</dd>
              <dt>映射版本</dt>
              <dd :title="ticket.prediction_mapping_version || undefined">
                {{ ticket.prediction_mapping_version?.slice(0, 12) || '同名对应' }}
              </dd>
              <dt>模型完整性</dt>
              <dd>{{ ticket.prediction_integrity }}</dd>
            </template>
            <dt>人工核对</dt>
            <dd>{{ ticket.needs_manual ? '需要人工确认' : '可自动路由' }}</dd>
          </dl></details>
          <details v-if="permissions.transfer || permissions.classify"><summary>转派与分类修正</summary>

          <form v-if="permissions.transfer" class="side-form" @submit.prevent="mutate('transfer')">
            <label for="assignee">转派客服</label>
            <ElSelect id="assignee" v-model="assignee" placeholder="选择符合分类组的客服" class="full">
              <ElOption v-for="agent in agents" :key="agent.id" :label="agent.display_name" :value="agent.id" />
            </ElSelect>
            <label for="transfer-reason">转派理由</label>
            <ElInput id="transfer-reason" v-model="transferReason" placeholder="必填：说明转派原因" maxlength="1000" />
            <ElButton :loading="busy" :disabled="conflict" native-type="submit">确认转派</ElButton>
          </form>

          <form v-if="permissions.classify" class="side-form" @submit.prevent="mutate('classify')">
            <label for="category">人工修正分类</label>
            <ElSelect id="category" v-model="category" placeholder="选择分类" class="full">
              <ElOption
                v-for="c in catalog.categories.filter((item) => item.active)"
                :key="c.id"
                :label="c.name"
                :value="c.id"
              />
            </ElSelect>
            <ElInput v-model="reason" placeholder="必填：纠错理由" aria-label="纠错理由" maxlength="1000" />
            <ElButton :loading="busy" :disabled="conflict" native-type="submit">保存分类修正</ElButton>
          </form>
          </details>
        </section>

        <section v-if="!isShop" class="panel">
          <h2>相关知识</h2>
          <ElButton @click="recommend">查找相关知识</ElButton>
          <ElAlert v-if="faqError" :title="faqError" type="error" />
          <FaqResults v-if="faq" :result="faq" />
        </section>
        <section v-else class="panel customer-progress">
          <template v-if="ticket.refund_stage">
            <details><summary>查看完整处理进度</summary>
            <ol class="case-track"><li v-for="step in milestones" :key="step.id">
              <strong>{{ step.label }}</strong><small>{{ formatTime(step.created_at) }}</small>
            </li></ol>
            </details>
          </template>
          <h2 v-else>关联订单</h2>
          <p v-if="ticket.order_no && !ticket.refund_stage">{{ ticket.order_no }} · {{ ticket.product_name || '商品' }}</p>
          <p v-else-if="!ticket.order_no" class="muted">此售后未绑定订单。</p>
        </section>
        <details v-if="!isShop || !ticket.refund_stage" class="panel case-history">
          <summary>处理历史</summary>
          <ElEmpty v-if="!ticket.events.length" description="暂无处理记录" :image-size="50" />
          <ol class="timeline">
            <li v-for="event in ticket.events" :key="event.id">
              <strong>{{ event.actor_name }}</strong> {{ event.detail }}
              <small>{{ formatTime(event.created_at) }}</small>
            </li>
          </ol>
        </details>
      </aside>
    </div>
  </div>
  </div>
</template>
