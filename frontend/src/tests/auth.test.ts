import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {auth,clearSession,restoreSession} from '../state/auth'
import type {User} from '../types'
beforeEach(()=>{clearSession();auth.ready=false;auth.expired=false})
afterEach(()=>{vi.unstubAllGlobals();clearSession()})
it('initial anonymous session lookup does not announce an expired session',async()=>{
 const expired=vi.fn();window.addEventListener('session-expired',expired)
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'请先登录'}),{status:401})))
 await restoreSession()
 window.removeEventListener('session-expired',expired)
 expect(expired).not.toHaveBeenCalled();expect(auth.user).toBeNull();expect(auth.ready).toBe(true)
})
it('a known authenticated session still announces its expiration on 401',async()=>{
 auth.user={id:1,username:'user',display_name:'用户',role:'user',active:true,group_id:null} as User
 const expired=vi.fn();window.addEventListener('session-expired',expired)
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'登录已过期'}),{status:401})))
 await restoreSession()
 window.removeEventListener('session-expired',expired)
 expect(expired).toHaveBeenCalledTimes(1);expect(auth.user).toBeNull()
})

it('a stale restore failure does not clear a later successful login',async()=>{
 const {login}=await import('../state/auth')
 let finishRestore!:(value:Response)=>void
 const newer={id:9,username:'newer',display_name:'新登录用户',role:'user',active:true,group_id:null}
 vi.stubGlobal('fetch',vi.fn(async(path:string)=>path.endsWith('/me')?new Promise<Response>(resolve=>{finishRestore=resolve}):new Response(JSON.stringify({user:newer,csrf_token:'newer-token'}))))
 const pending=restoreSession()
 await login('newer','DEMO-only-long-password')
 finishRestore(new Response(JSON.stringify({detail:'旧会话失效'}),{status:401}))
 await pending
 expect(auth.user?.username).toBe('newer')
})

it('a stale successful restore cannot replace a newer login identity',async()=>{
 const {login}=await import('../state/auth')
 let finishRestore!:(value:Response)=>void
 const newer={id:9,username:'newer',display_name:'新用户',role:'user',active:true,group_id:null}
 vi.stubGlobal('fetch',vi.fn(async(path:string)=>path.endsWith('/me')?new Promise<Response>(resolve=>{finishRestore=resolve}):new Response(JSON.stringify({user:newer,csrf_token:'newer-token'}))))
 const pending=restoreSession()
 await login('newer','DEMO-only-long-password')
 finishRestore(new Response(JSON.stringify({user:{...newer,id:1,username:'old'},csrf_token:'older-token'})))
 await pending
 expect(auth.user?.username).toBe('newer')
})
