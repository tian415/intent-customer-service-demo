import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import App from '../App.vue'
import { auth, clearSession, logout } from '../state/auth'

const user = { id: 1, username: 'customer', display_name: '用户', role: 'user' as const, active: true, group_id: null }
let wrapper: VueWrapper | undefined

beforeEach(() => {
  clearSession()
  auth.ready = true
  auth.expired = false
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.unstubAllGlobals()
  clearSession()
})

async function setup(path = '/shop') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/shop/login', component: { template: '<p>顾客登录</p>' } },
      { path: '/staff/login', component: { template: '<p>员工登录</p>' } },
      { path: '/shop', component: { template: '<p>顾客页</p>' } },
      { path: '/:pathMatch(.*)*', component: { template: '<p>其他页面</p>' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  wrapper = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return router
}

it('late unauthorized response after clearing a session does not announce expiration', async () => {
  auth.user = user
  const router = await setup()
  clearSession()
  window.dispatchEvent(new Event('session-expired'))
  await flushPromises()
  expect(auth.expired).toBe(false)
  expect(router.currentRoute.value.path).toBe('/shop')
})

it('active session expiration still clears user and opens matching login', async () => {
  auth.user = user
  const router = await setup()
  window.dispatchEvent(new Event('session-expired'))
  await flushPromises()
  expect(auth.user).toBeNull()
  expect(auth.expired).toBe(true)
  expect(router.currentRoute.value.path).toBe('/shop/login')
})

it('unmounted shell removes its expiration event listener', async () => {
  await setup()
  wrapper!.unmount()
  wrapper = undefined
  auth.user = user
  window.dispatchEvent(new Event('session-expired'))
  await flushPromises()
  expect(auth.user).toEqual(user)
  expect(auth.expired).toBe(false)
})

it('manual logout clears any previous expiration message', async () => {
  auth.user = user
  auth.expired = true
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }))))
  await logout()
  expect(auth.user).toBeNull()
  expect(auth.expired).toBe(false)
})

it('reload warns for an unsent draft on another ticket, and disarms after logout', async () => {
  const {ticketDraft} = await import('../state/ticketWorkspace')
  auth.user = user
  await setup('/shop/orders')
  const before = new Event('beforeunload', {cancelable: true})
  window.dispatchEvent(before)
  expect(before.defaultPrevented).toBe(false)
  ticketDraft(user.id, '42').privateText = '尚未发送的内容'
  const during = new Event('beforeunload', {cancelable: true})
  window.dispatchEvent(during)
  expect(during.defaultPrevented).toBe(true)
  clearSession()
  const after = new Event('beforeunload', {cancelable: true})
  window.dispatchEvent(after)
  expect(after.defaultPrevented).toBe(false)
})
