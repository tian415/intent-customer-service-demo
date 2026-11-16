import { afterEach, expect, it, vi } from 'vitest'
import { api, setCsrf } from '../api/client'

afterEach(() => { vi.unstubAllGlobals(); setCsrf('') })

it('a 401 from an earlier login cannot expire a newly authenticated session', async () => {
  let finishOld!:(value:Response)=>void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finishOld=resolve })))
  setCsrf('old-session')
  const oldRequest=api('/tickets')
  const outcome=expect(oldRequest).rejects.toMatchObject({status:401})
  setCsrf('new-session')
  const expired=vi.fn()
  window.addEventListener('session-expired',expired)
  try {
    finishOld(new Response(JSON.stringify({detail:'旧会话已失效'}),{status:401}))
    await outcome
    expect(expired).not.toHaveBeenCalled()
  } finally { window.removeEventListener('session-expired',expired) }
})
