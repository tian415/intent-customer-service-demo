export type Role = 'user' | 'agent' | 'admin'
export interface User { id:number; username:string; display_name:string; role:Role; active:boolean; group_id:number|null }
export interface Group { id:number; name:string }
export interface Category extends Group { keywords:string; active:boolean; group_id:number|null }
export interface FAQ { id:number; question:string; answer:string; keywords:string; category_id:number|null; active:boolean; score?:number }
export type TicketStatus = 'pending'|'assigned'|'processing'|'resolved'|'closed'
export interface Ticket {
  id:number
  title:string
  description:string
  status:TicketStatus
  owner_id:number
  refund_stage?:RefundStage|null
  owner_name:string
  assignee_id:number|null
  assignee_name:string|null
  category_id:number|null
  category_name:string|null
  group_id:number|null
  order_id?:number|null
  order_no?:string|null
  product_name?:string|null
  version:number
  created_at:string
  updated_at:string
  prediction_source:string
  prediction_model_version?:string|null
  prediction_label?:string|null
  prediction_mapping_version?:string|null
  prediction_integrity?:string|null
  prediction_score:number|null
  needs_manual:boolean
  needs_staff_reply?:boolean
  latest_public_reply?:{body:string;created_at:string;from_customer:boolean}|null
}
export interface TicketDetail extends Ticket { order?:Order|null; customer_statements?:string[]; messages:{id:number;author_id?:number;author_name:string;body:string;internal:boolean;created_at:string}[]; events:{id:number;actor_name:string;kind:string;detail:string;created_at:string}[] }
export interface Catalog { categories:Category[]; groups:Group[]; agents:User[] }
export interface FaqResult { items:FAQ[]; reliable:boolean; source:string; fallback:string|null }
export interface Stats { total:number; by_status:{name:string;count:number}[]; by_category:{name:string;count:number}[]; by_source:{name:string;count:number}[]; corrections:number; unassigned:number }
export type RefundStage = 'requested'|'approved'|'declined'
export const refundLabels:Record<RefundStage,string> = {requested:'等待客服审核',approved:'审核通过',declined:'未通过审核'}
export interface OrderAftersale { refund_stage?:RefundStage|null; id:number; title:string; status:string; status_label:string; updated_at:string }
export interface Order {
  id:number
  order_no:string
  product_name:string
  status:string
  status_label:string
  amount_cents:number
  amount_display:string
  created_at:string
  updated_at:string
  aftersales?:OrderAftersale[]
}
export type ConversationStatus = 'active'|'waiting_order'|'handed_off'|'closed'
export interface ConversationMessage { id:number; role:'user'|'assistant'|'system'|'agent'; body:string; created_at:string }
export interface ConversationDetail {
  id:number
  status:ConversationStatus
  status_label:string
  stage:string
  service_intent?:'get_refund'|'track_refund'|'check_refund_policy'|'refund_timing'|'clarify_refund'|'refund_submission_help'|null
  recent_cases?:{id:number;product:string;refund_stage:RefundStage|null;status_label:string}[]
  can_submit_refund?:boolean
  related_refund_id?:number|null
  current_request:string|null
  next_action:'ask_order'|'clarify'|'answer'|'handoff'|null
  selected_order_id:number|null
  selected_order:Order|null
  ticket_id:number|null
  version:number
  prediction_source:string|null
  prediction_source_label?:string|null
  prediction_model_version?:string|null
  prediction_label?:string|null
  prediction_label_display?:string|null
  prediction_mapping_version?:string|null
  prediction_integrity?:string|null
  prediction_score:number|null
  needs_manual:boolean
  quick_replies:string[]
  created_at:string
  updated_at:string
  messages:ConversationMessage[]
  orders:Order[]
}
export const statusLabels:Record<TicketStatus,string> = {pending:'待分配',assigned:'已分配',processing:'处理中',resolved:'待确认',closed:'已关闭'}
export const roleLabels:Record<Role,string> = {user:'用户',agent:'客服',admin:'管理员'}
export const formatTime = (value:string) => new Date(value).toLocaleString('zh-CN')
export function homePath(role?: Role | null): string {
  if (role === 'user') return '/shop'
  if (role === 'admin') return '/staff/admin/stats'
  if (role === 'agent') return '/staff/tickets'
  return '/'
}
export function loginPath(role?: Role | null): string {
  if (role === 'user') return '/shop/login'
  if (role === 'agent' || role === 'admin') return '/staff/login'
  return '/'
}
export function isStaff(role?: Role | null): boolean {
  return role === 'agent' || role === 'admin'
}

export const predictionSourceLabels: Record<string, string> = { rules: '关键词匹配', model: '本地意图模型', fallback: '人工确认', manual: '人工分类' }
