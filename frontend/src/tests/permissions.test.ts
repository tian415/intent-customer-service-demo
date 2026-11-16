import { expect,it } from 'vitest'
import { ticketPermissions } from '../state/tickets'
import type { TicketDetail, User } from '../types'
const user={id:1,role:'user',group_id:null} as User
const ticket={owner_id:1,assignee_id:2,status:'processing',group_id:3} as TicketDetail
it('owner cannot solve or see staff actions and can confirm only resolved tickets',()=>{expect(ticketPermissions(ticket,user)).toMatchObject({resolve:false,transfer:false,classify:false,close:false});expect(ticketPermissions({...ticket,status:'resolved'},user).close).toBe(true)})
it('only eligible agent can accept and only assignee can resolve',()=>{const agent={id:2,role:'agent',group_id:3} as User;expect(ticketPermissions(ticket,agent).resolve).toBe(true);expect(ticketPermissions(ticket,{...agent,id:4}).resolve).toBe(false);expect(ticketPermissions({...ticket,status:'pending',assignee_id:null},agent).accept).toBe(true)})
it('resolved tickets forbid messages and transfer but allow owner reopen',()=>{expect(ticketPermissions({...ticket,status:'resolved'},user)).toMatchObject({reply:false,reopen:true});expect(ticketPermissions({...ticket,status:'resolved'},{...user,role:'admin'}).transfer).toBe(false)})
it('staff actions match backend handler rules',()=>{
 const admin={...user,role:'admin'} as User,other={...user,id:4,role:'agent',group_id:3} as User
 expect(ticketPermissions({...ticket,status:'assigned'},admin).accept).toBe(false)
 expect(ticketPermissions(ticket,other)).toMatchObject({reply:false,classify:false})
 expect(ticketPermissions({...ticket,status:'resolved'},admin).classify).toBe(false)
})
