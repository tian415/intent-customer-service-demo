import { reactive } from 'vue'

export interface TicketDraft {
  publicText: string
  privateText: string
  decisionText: string
  followupText: string
  refundDecision: string
  reviewVersion: number | null
  mode: 'reply' | 'internal' | 'resolve'
}

// In-memory only: retain work across routes, discard it on logout/account change.
const drafts = new Map<string, TicketDraft>()
export const queueFilters = reactive({ scope: 'todo', query: '', status: '', page: 1 })
export function ticketDraft(userId: number, ticketId: string): TicketDraft {
  const key = `${userId}:${ticketId}`
  let draft = drafts.get(key)
  if (!draft) {
    draft = reactive<TicketDraft>({ publicText: '', privateText: '', decisionText: '', followupText: '', refundDecision: '', reviewVersion: null, mode: 'reply' })
    drafts.set(key, draft)
  }
  return draft
}
export function clearTicketWorkspace() { drafts.clear(); Object.assign(queueFilters, { scope: 'todo', query: '', status: '', page: 1 }) }

export function hasTicketDrafts(userId: number): boolean {
  return [...drafts].some(([key, draft]) => key.startsWith(`${userId}:`)
    && [draft.publicText, draft.privateText, draft.decisionText, draft.followupText].some(text => text.trim()))
}

export function announceTicketChange() { window.dispatchEvent(new Event('ticket-changed')) }
