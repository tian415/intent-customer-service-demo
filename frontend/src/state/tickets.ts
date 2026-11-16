import type { Ticket,User } from '../types'
export function ticketPermissions(t:Ticket,u:User){
  const staff=u.role!=='user',admin=u.role==='admin',own=t.owner_id===u.id&&u.role==='user',assignee=t.assignee_id===u.id,open=t.status!=='closed'&&t.status!=='resolved'
  return {
    staff,
    reply:open&&(u.role==='user'||admin||assignee),
    accept:(t.status==='pending'||t.status==='assigned')&&u.role==='agent'&&(assignee||t.assignee_id===null&&(t.group_id===null||t.group_id===u.group_id)),
    resolve:t.status==='processing'&&(admin||assignee),
    close:own&&t.status==='resolved',
    reopen:own&&!open,
    transfer:open&&(admin||assignee),
    classify:open&&staff&&(admin||assignee||t.assignee_id===null),
  }
}
