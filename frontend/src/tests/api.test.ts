import { afterEach, expect, it, vi } from 'vitest'
import { api, ApiError, setCsrf } from '../api/client'
afterEach(() => { vi.unstubAllGlobals(); setCsrf('') })
it('sends CSRF and mutation identification with cookies', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetcher); setCsrf('secret')
  await api('/tickets', { method: 'POST', body: { title: 'test' } })
  expect(fetcher.mock.calls[0]?.[1]).toMatchObject({ credentials: 'same-origin', headers: expect.objectContaining({ 'X-CSRF-Token': 'secret', 'X-Requested-With': 'ticket-ui' }) })
})
it('preserves Chinese API errors and conflict status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'工单已更新，请刷新'}), {status:409})))
  await expect(api('/tickets/1')).rejects.toMatchObject({ status:409, message:'工单已更新，请刷新' })
})
it('turns validation arrays and network errors into useful messages', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:[{loc:['body','title'],msg:'必填'}]}), {status:422})))
  await expect(api('/tickets')).rejects.toThrow('title：必填')
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
  await expect(api('/tickets')).rejects.toBeInstanceOf(ApiError)
})

it('invalid sessions notify the shell but invalid login stays on its form', async () => {
  const expired = vi.fn(); window.addEventListener('session-expired', expired)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'登录已过期'}), {status:401})))
  await expect(api('/auth/me')).rejects.toMatchObject({status:401})
  expect(expired).toHaveBeenCalledTimes(1)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'账号或密码错误'}), {status:401})))
  await expect(api('/auth/login', {method:'POST',body:{}})).rejects.toMatchObject({status:401})
  expect(expired).toHaveBeenCalledTimes(1)
  window.removeEventListener('session-expired', expired)
})
