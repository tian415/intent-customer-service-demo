import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import ShopLoginPage from '../pages/ShopLoginPage.vue'
import StaffLoginPage from '../pages/StaffLoginPage.vue'
import TicketPage from '../pages/TicketPage.vue'
import AdminPage from '../pages/AdminPage.vue'
import SupportPage from '../pages/SupportPage.vue'
import ShopOrdersPage from '../pages/ShopOrdersPage.vue'
import { auth, clearSession } from '../state/auth'
import type { User, TicketDetail, ConversationDetail } from '../types'

const mounted: VueWrapper[] = []
const user: User = { id: 1, username: 'customer', display_name: '用户', role: 'user', active: true, group_id: null }
const ticket: TicketDetail = {
  id: 10,
  title: '登录问题',
  description: '无法登录',
  status: 'processing',
  owner_id: 1,
  owner_name: '用户',
  assignee_id: 2,
  assignee_name: '客服',
  category_id: 1,
  category_name: '账号',
  group_id: 1,
  order_id: 1,
  order_no: 'T-1001',
  product_name: '测试耳机',
  version: 1,
  created_at: '2026-10-28T00:00:00Z',
  updated_at: '2026-10-28T00:00:00Z',
  prediction_source: 'rules',
  prediction_score: 1,
  needs_manual: false,
  messages: [],
  events: [],
}
const conversation: ConversationDetail = {
  id: 7,
  status: 'active',
  status_label: '接待中',
  stage: 'greeting',
  next_action: null,
  current_request: null,
  selected_order_id: null,
  selected_order: null,
  ticket_id: null,
  version: 2,
  prediction_source: null,
  prediction_source_label: null,
  prediction_label_display: null,
  prediction_score: 0,
  needs_manual: true,
  quick_replies: ['查询物流进度', '我想申请退款', '转人工客服'],
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
  messages: [
    { id: 1, role: 'assistant', body: '您好，售后助手', created_at: '2026-11-03T00:00:00Z' },
    { id: 2, role: 'system', body: '下面有你的订单卡片', created_at: '2026-11-03T00:00:00Z' },
  ],
  orders: [{
    id: 1,
    order_no: 'T-1001',
    product_name: '测试耳机',
    status: 'shipped',
    status_label: '已发货',
    amount_cents: 9900,
    amount_display: '¥99.00',
    created_at: '2026-11-03T00:00:00Z',
    updated_at: '2026-11-03T00:00:00Z',
  }],
}
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })

async function setup(
  component: typeof ShopLoginPage | typeof StaffLoginPage | typeof TicketPage | typeof AdminPage | typeof SupportPage | typeof ShopOrdersPage,
  path = '/shop/login',
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/staff/admin/:section?', component: AdminPage },
      { path: '/shop/login', component: ShopLoginPage },
      { path: '/staff/login', component: StaffLoginPage },
      { path: '/shop', component: SupportPage },
      { path: '/shop/orders', component: ShopOrdersPage },
      { path: '/shop/tickets/:id', component: TicketPage },
      { path: '/staff/tickets/:id', component: TicketPage },
      { path: '/staff/tickets', component: { template: '<p>工单列表</p>' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, { global: { plugins: [router] } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  clearSession()
  auth.ready = true
  auth.expired = false
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})
afterEach(() => {
  mounted.forEach((w) => w.unmount())
  mounted.length = 0
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it('shop login reports server errors and keeps username for correction', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: '账号或密码错误' }, 401)))
  const { wrapper, router } = await setup(ShopLoginPage)
  await wrapper.get('#shop-username').setValue('customer')
  await wrapper.get('#shop-password').setValue('bad password')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('账号或密码错误')
  expect((wrapper.get('#shop-username').element as HTMLInputElement).value).toBe('customer')
  expect(router.currentRoute.value.path).toBe('/shop/login')
})

it('successful shop login opens support home for users', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ user, csrf_token: 'test-csrf' })))
  const { wrapper, router } = await setup(ShopLoginPage)
  await wrapper.get('#shop-username').setValue('customer')
  await wrapper.get('#shop-password').setValue('strong password')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(auth.user?.username).toBe('customer')
  expect(router.currentRoute.value.path).toBe('/shop')
  expect(localStorage.length).toBe(0)
})

it('shop login rejects staff accounts', async () => {
  const fetcher = vi.fn().mockResolvedValue(response({ detail: '这是顾客入口。请使用员工入口登录。' }, 403))
  vi.stubGlobal('fetch', fetcher)
  const { wrapper } = await setup(ShopLoginPage)
  await wrapper.get('#shop-username').setValue('agent')
  await wrapper.get('#shop-password').setValue('strong password')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(JSON.parse(fetcher.mock.calls[0]![1].body).portal).toBe('shop')
  expect(wrapper.text()).toContain('请使用员工入口登录')
  expect(auth.user).toBeNull()
})

it('ticket owner cannot see staff actions; conflicting reply preserves input', async () => {
  auth.user = user
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) =>
    input.endsWith('/catalog')
      ? response({ categories: [], groups: [], agents: [] })
      : init?.method === 'POST'
        ? response({ detail: '工单版本过期' }, 409)
        : response(ticket)))
  const { wrapper } = await setup(TicketPage, '/shop/tickets/10')
  expect(wrapper.text()).not.toContain('标记已解决')
  expect(wrapper.text()).not.toContain('内部备注')
  expect(wrapper.text()).not.toContain('转派客服')
  expect(wrapper.text()).toContain('T-1001')
  await wrapper.get('#reply').setValue('请帮忙核查')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('其他人已更新此工单')
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('请帮忙核查')
})

it('assigned staff can resolve and choose internal note visibility', async () => {
  auth.user = { ...user, id: 2, role: 'agent', group_id: 1 }
  const fetcher = vi.fn(async (input: string, init?: RequestInit) =>
    input.endsWith('/catalog')
      ? response({ categories: [], groups: [], agents: [] })
      : init?.method === 'POST'
        ? response({ ...ticket, version: 2 })
        : response(ticket))
  vi.stubGlobal('fetch', fetcher)
  const { wrapper } = await setup(TicketPage, '/staff/tickets/10')
  expect(wrapper.text()).toContain('提交处理结果')
  expect(wrapper.text()).toContain('转派客服')
  await wrapper.get('#reply').setValue('给顾客的草稿')
  await wrapper.findAll('button').find(button => button.text() === '写内部备注')!.trigger('click')
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('')
  await wrapper.get('#reply').setValue('请核对后台日志')
  await wrapper.get('.reply-form').trigger('submit')
  await flushPromises()
  const call = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ internal: true, body: '请核对后台日志', version: 1 })
})

it('late ticket load cannot overwrite a newer route', async () => {
  auth.user = user
  let finishOld!: (value: Response) => void
  vi.stubGlobal('fetch', vi.fn(async (input: string) =>
    input.endsWith('/catalog')
      ? response({ categories: [], groups: [], agents: [] })
      : input.endsWith('/10')
        ? new Promise<Response>((resolve) => { finishOld = resolve })
        : response({ ...ticket, id: 11, title: '新工单' })))
  const { wrapper, router } = await setup(TicketPage, '/shop/tickets/10')
  await router.push('/shop/tickets/11')
  await flushPromises()
  expect(wrapper.text()).toContain('新工单')
  finishOld(response(ticket))
  await flushPromises()
  expect(wrapper.text()).toContain('新工单')
  expect(wrapper.text()).not.toContain('登录问题')
})

it('failed detail navigation clears the old ticket and its draft', async () => {
  auth.user = user
  vi.stubGlobal('fetch', vi.fn(async (input: string) =>
    input.endsWith('/catalog')
      ? response({ categories: [], groups: [], agents: [] })
      : input.endsWith('/10')
        ? response(ticket)
        : response({ detail: '工单不存在' }, 404)))
  const { wrapper, router } = await setup(TicketPage, '/shop/tickets/10')
  await wrapper.get('#reply').setValue('旧草稿')
  await router.push('/shop/tickets/11')
  await flushPromises()
  expect(wrapper.text()).toContain('工单不存在')
  expect(wrapper.text()).not.toContain('登录问题')
  expect(wrapper.find('#reply').exists()).toBe(false)
})

it('late mutation result cannot replace the next ticket', async () => {
  auth.user = user
  let finishMutation!: (value: Response) => void
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) =>
    input.endsWith('/catalog')
      ? response({ categories: [], groups: [], agents: [] })
      : init?.method === 'POST'
        ? new Promise<Response>((resolve) => { finishMutation = resolve })
        : response(input.endsWith('/10') ? ticket : { ...ticket, id: 11, title: '另一工单' })))
  const { wrapper, router } = await setup(TicketPage, '/shop/tickets/10')
  await wrapper.get('#reply').setValue('旧回复')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  await router.push('/shop/tickets/11')
  await flushPromises()
  finishMutation(response({ ...ticket, version: 2 }))
  await flushPromises()
  expect(wrapper.text()).toContain('另一工单')
  expect(wrapper.text()).not.toContain('登录问题')
})

it('admin FAQ fields match backend character limits', async () => {
  auth.user = { ...user, role: 'admin' }
  vi.stubGlobal('fetch', vi.fn(async (input: string) =>
    response(input.endsWith('/stats')
      ? { total: 0, by_status: [], by_category: [], by_source: [], corrections: 0, unassigned: 0 }
      : [])))
  const { wrapper } = await setup(AdminPage, '/staff/admin/faqs')
  await wrapper.findAll('button').find((button) => button.text() === '新增知识')!.trigger('click')
  expect(wrapper.get('#faq-question').attributes('maxlength')).toBe('300')
  expect(wrapper.get('#keywords').attributes('maxlength')).toBe('1000')
})

it('transfer requires a reason and submits it with version', async () => {
  auth.user = { ...user, id: 2, role: 'agent', group_id: 1 }
  const fetcher = vi.fn(async (input: string, init?: RequestInit) =>
    input.endsWith('/catalog')
      ? response({
        categories: [{ id: 1, name: '账号', group_id: 1, active: true, keywords: '' }],
        groups: [],
        agents: [{ ...user, id: 3, role: 'agent', group_id: 1, display_name: '客服三' }],
      })
      : response(init?.method === 'POST' ? { ...ticket, version: 2, assignee_id: 3 } : ticket))
  vi.stubGlobal('fetch', fetcher)
  const { wrapper } = await setup(TicketPage, '/staff/tickets/10')
  const { ElSelect } = await import('element-plus')
  wrapper.findAllComponents(ElSelect)[0]!.vm.$emit('update:modelValue', 3)
  await wrapper.get('form:has(#transfer-reason)').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('请选择目标客服并填写转派理由')
  await wrapper.get('#transfer-reason').setValue('需要其他客服进一步核查')
  await wrapper.get('form:has(#transfer-reason)').trigger('submit')
  await flushPromises()
  const call = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
    action: 'transfer',
    assignee_id: 3,
    reason: '需要其他客服进一步核查',
    version: 1,
  })
})

it('refresh losing access removes previous ticket actions', async () => {
  auth.user = { ...user, id: 2, role: 'agent', group_id: 1 }
  let allowed = true
  vi.stubGlobal('fetch', vi.fn(async (input: string) =>
    input.endsWith('/catalog')
      ? response({ categories: [], groups: [], agents: [] })
      : allowed
        ? response(ticket)
        : response({ detail: '工单不存在或无访问权限' }, 404)))
  const { wrapper } = await setup(TicketPage, '/staff/tickets/10')
  expect(wrapper.text()).toContain('提交处理结果')
  allowed = false
  await wrapper.findAll('button').find((button) => button.text() === '刷新')!.trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('返回工单台')
  expect(wrapper.text()).not.toContain('标记已解决')
})

it('admin tab changes discard earlier load results', async () => {
  auth.user = { ...user, role: 'admin' }
  let finishOld!: (value: Response) => void
  let groupLoads = 0
  let userLoads = 0
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    if (input.endsWith('/users') && ++userLoads === 1) return new Promise<Response>((resolve) => { finishOld = resolve })
    if (input.endsWith('/groups')) return response([{ id: 1, name: ++groupLoads === 1 ? '旧客服组' : '新客服组' }])
    return response(input.endsWith('/stats')
      ? { total: 0, by_status: [], by_category: [], by_source: [], corrections: 0, unassigned: 0 }
      : [])
  }))
  const { wrapper, router } = await setup(AdminPage, '/staff/admin/users')
  await router.push('/staff/admin/groups')
  await flushPromises()
  expect(wrapper.text()).toContain('新客服组')
  finishOld(response([]))
  await flushPromises()
  expect(wrapper.text()).toContain('新客服组')
  expect(wrapper.text()).not.toContain('旧客服组')
})

it('support page starts a session, selects an order, and confirms handoff', async () => {
  auth.user = user
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith('/conversations') && init?.method === 'POST') {
      const payload = JSON.parse(String(init?.body ?? '{}')) as { force_new?: boolean }
      expect(payload.force_new === true || payload.force_new === false).toBe(true)
      return response(conversation)
    }
    if (String(input).includes('/actions')) {
      const payload = JSON.parse(String(init?.body ?? '{}')) as { action?: string }
      if (payload.action === 'select_order') {
        return response({
          ...conversation,
          version: 3,
          status: 'active',
          status_label: '接待中',
          stage: 'order_bound',
          current_request: '查物流',
          selected_order_id: 1,
          selected_order: conversation.orders[0],
          prediction_label_display: '查询物流',
          prediction_source_label: '关键词匹配',
          quick_replies: ['查询物流进度', '我想申请退款', '转人工处理'],
          messages: [...conversation.messages, { id: 5, role: 'assistant', body: '已关联订单并继续处理', created_at: '2026-11-03T00:02:00Z' }],
        })
      }
      return response({
        ...conversation,
        version: 4,
        status: 'handed_off',
        status_label: '已转人工',
        stage: 'handed_off',
        ticket_id: 88,
        selected_order_id: 1,
        selected_order: conversation.orders[0],
        quick_replies: [],
      })
    }
    if (String(input).includes('/messages')) {
      return response({
        ...conversation,
        version: 3,
        status: 'waiting_order',
        status_label: '待选择订单',
        stage: 'await_order',
        current_request: '查物流',
        quick_replies: ['我先选一笔订单'],
        messages: [
          ...conversation.messages,
          { id: 3, role: 'user', body: '查物流', created_at: '2026-11-03T00:01:00Z' },
          { id: 4, role: 'assistant', body: '请先点选订单', created_at: '2026-11-03T00:01:00Z' },
        ],
      })
    }
    return response(conversation)
  })
  vi.stubGlobal('fetch', fetcher)
  const { wrapper } = await setup(SupportPage, '/shop')
  expect(wrapper.text()).toContain('售后助手')
  expect(wrapper.find('a[href^="/shop/orders"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('T-1001')
  expect(wrapper.text()).not.toContain('说明问题')
  expect(wrapper.text()).not.toContain('本次理解')
  await wrapper.get('#support-draft').setValue('查物流')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('请先点选订单')
  expect(wrapper.text()).toContain('T-1001')
  await wrapper.get('.wx-order-card').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('已关联订单并继续处理')
  await wrapper.findAll('button').find((button) => button.text().includes('人工') && !button.text().includes('确认'))!.trigger('click')
  await flushPromises()
  await wrapper.findAll('button').find((button) => button.text() === '确认提交人工')!.trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('售后进度')
})

it('shop orders page shows aftersales entry for each order', async () => {
  auth.user = user
  vi.stubGlobal('fetch', vi.fn(async (path: string) => path.includes('/tickets?scope=mine')
    ? response({ items: [{ ...ticket, id: 89, order_no: null, title: '找回密码' }], total: 1 })
    : response([{
    id: 1,
    order_no: 'T-1001',
    product_name: '测试耳机',
    status: 'shipped',
    status_label: '已发货',
    amount_cents: 9900,
    amount_display: '¥99.00',
    created_at: '2026-11-03T00:00:00Z',
    updated_at: '2026-11-03T00:00:00Z',
    aftersales: [{ id: 88, title: '查物流', status: 'processing', status_label: '处理中', updated_at: '2026-11-03T00:00:00Z' }],
  }])))
  const { wrapper } = await setup(ShopOrdersPage, '/shop/orders')
  expect(wrapper.text()).toContain('#89 找回密码')
  expect(wrapper.text()).toContain('未关联订单')
  await wrapper.findAll('button').find(b => b.text() === '我的订单')!.trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('T-1001')
  expect(wrapper.text()).toContain('#88 查物流')
  expect(wrapper.text()).toContain('处理中')
})

it('staff login opens ticket desk for agents', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
    user: { ...user, id: 2, username: 'agent', role: 'agent', group_id: 1 },
    csrf_token: 'csrf',
  })))
  const { wrapper, router } = await setup(StaffLoginPage, '/staff/login')
  await wrapper.get('#staff-username').setValue('agent')
  await wrapper.get('#staff-password').setValue('strong password')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/staff/tickets')
})

it('polling brings in a staff reply without clearing the customer draft', async () => {
  auth.user = user
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  let current = ticket
  vi.stubGlobal('fetch', vi.fn(async (path: string) => response(path.endsWith('/catalog') ? {categories:[],groups:[],agents:[]} : current)))
  const {wrapper} = await setup(TicketPage, '/shop/tickets/10')
  await wrapper.get('#reply').setValue('还有一个细节正在输入')
  current = {...ticket,version:2,messages:[{id:1,author_id:2,author_name:'客服',body:'已收到您的问题，请补充情况',internal:false,created_at:ticket.updated_at}]}
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(wrapper.text()).toContain('收到客服的新回复')
  expect(wrapper.text()).toContain('已收到您的问题，请补充情况')
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('还有一个细节正在输入')
})

it('reply, internal and decision drafts survive ticket changes and clear on logout', async () => {
  auth.user = {...user,id:2,role:'agent',group_id:1}
  vi.stubGlobal('fetch', vi.fn(async (path:string) => response(path.endsWith('/catalog') ? {categories:[],groups:[],agents:[]} : {...ticket,id:path.endsWith('/11')?11:10})))
  const {wrapper,router} = await setup(TicketPage,'/staff/tickets/10')
  await wrapper.get('#reply').setValue('顾客回复草稿')
  const click = async (text:string) => wrapper.findAll('button').find(b=>b.text()===text)!.trigger('click')
  await click('写内部备注')
  await wrapper.get('#reply').setValue('内部记录草稿')
  await click('提交处理结果')
  await wrapper.get('#reply').setValue('处理意见草稿')
  await router.push('/staff/tickets/11'); await flushPromises()
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('')
  await wrapper.get('#reply').setValue('另一个工单的草稿')
  await router.push('/staff/tickets/10'); await flushPromises()
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('处理意见草稿')
  await click('写内部备注')
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('内部记录草稿')
  await click('回复顾客')
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('顾客回复草稿')
  clearSession(); await flushPromises()
  auth.user = {...user,id:2,role:'agent',group_id:1}; await flushPromises()
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('')
})

it('new customer input requires review before submitting an existing decision draft', async () => {
  auth.user = {...user,id:2,role:'agent',group_id:1}
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  let current = ticket
  vi.stubGlobal('fetch', vi.fn(async(path:string) => response(path.endsWith('/catalog') ? {categories:[],groups:[],agents:[]} : current)))
  const {wrapper}=await setup(TicketPage,'/staff/tickets/10')
  await wrapper.findAll('button').find(b=>b.text()==='提交处理结果')!.trigger('click')
  await wrapper.get('#reply').setValue('原处理意见尚未发送')
  current={...ticket,version:2,messages:[{id:1,author_id:1,author_name:'用户',body:'补充新的情况',internal:false,created_at:ticket.updated_at}]}
  window.dispatchEvent(new Event('focus')); await flushPromises()
  expect(wrapper.text()).toContain('工单有更新，请核对最新消息后提交')
  expect(wrapper.findAll('button').find(b=>b.text()==='发送处理结果')!.attributes('disabled')).toBeDefined()
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('原处理意见尚未发送')
})

it('a polling request started before a reply cannot roll back the sent result', async () => {
  auth.user=user
  vi.spyOn(document,'hidden','get').mockReturnValue(false)
  let getCount=0, finishPoll!:(value:Response)=>void
  vi.stubGlobal('fetch',vi.fn(async(path:string,init?:RequestInit)=>{
    if(path.endsWith('/catalog')) return response({categories:[],groups:[],agents:[]})
    if(init?.method==='POST') return response({...ticket,version:3,messages:[{id:2,author_name:'用户',body:'已经发送的回复',internal:false,created_at:ticket.updated_at}]})
    if(++getCount===1) return response(ticket)
    return new Promise<Response>(resolve=>{finishPoll=resolve})
  }))
  const {wrapper}=await setup(TicketPage,'/shop/tickets/10')
  window.dispatchEvent(new Event('focus')); await flushPromises()
  await wrapper.get('#reply').setValue('已经发送的回复')
  await wrapper.get('.reply-form').trigger('submit'); await flushPromises()
  finishPoll(response({...ticket,version:2})); await flushPromises()
  expect(wrapper.text()).toContain('已经发送的回复')
  expect((wrapper.get('#reply').element as HTMLTextAreaElement).value).toBe('')
})

it('customer feedback uses one follow-up action and preserves the original ticket',async()=>{
  auth.user=user
  const fetcher=vi.fn(async(path:string,init?:RequestInit)=>response(path.endsWith('/catalog')?{categories:[],groups:[],agents:[]}:init?.method==='POST'?{...ticket,version:3,status:'assigned'}:{...ticket,status:'resolved'}))
  vi.stubGlobal('fetch',fetcher)
  const {wrapper}=await setup(TicketPage,'/shop/tickets/10')
  await wrapper.findAll('button').find(b=>b.text()==='问题还没解决')!.trigger('click')
  await wrapper.get('#reply').setValue('照做后依然无法登录')
  await wrapper.get('.reply-form').trigger('submit'); await flushPromises()
  const writes=fetcher.mock.calls.filter(([,init])=>init?.method==='POST')
  expect(writes).toHaveLength(1)
  expect(writes[0]![0]).toBe('/api/tickets/10/actions')
  expect(JSON.parse(String(writes[0]![1]?.body))).toMatchObject({action:'follow_up',reason:'照做后依然无法登录',version:1})
  expect(wrapper.text()).toContain('补充已发送')
})
