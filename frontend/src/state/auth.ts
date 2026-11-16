import { reactive } from 'vue'
import { api, setCsrf, getSessionRevision } from '../api/client'
import type { User } from '../types'
import { clearTicketWorkspace } from './ticketWorkspace'
export const auth = reactive<{user:User|null;ready:boolean;expired:boolean}>({user:null,ready:false,expired:false})
function apply(result:{user:User;csrf_token:string}) { auth.user=result.user;setCsrf(result.csrf_token);auth.expired=false }
export async function restoreSession() {
  const revision = getSessionRevision()
  try {
    const result = await api<{user:User;csrf_token:string}>('/auth/me',{notifyUnauthorized:auth.user!==null})
    if (revision === getSessionRevision()) apply(result)
  } catch { if (revision === getSessionRevision()) auth.user=null }
  finally { auth.ready=true }
}
export async function login(username: string, password: string, portal?: 'shop' | 'staff') {
  const result = await api<{user:User;csrf_token:string}>('/auth/login', { method: 'POST', body: { username, password, portal } })
  clearTicketWorkspace()
  apply(result)
  auth.ready = true
}
export async function logout() { await api('/auth/logout',{method:'POST',body:{}});clearSession() }
export function clearSession() { clearTicketWorkspace();auth.user=null;auth.expired=false;setCsrf('') }
