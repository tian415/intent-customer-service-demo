// Independent authenticated customer/staff browsers, using the disposable fixture.
import assert from 'node:assert/strict'
import {readFileSync, writeFileSync} from 'node:fs'
import {join} from 'node:path'
import {chromium} from 'playwright-core'

const {origin, credentials, output} = JSON.parse(readFileSync(0,'utf8'))
const checks=[]
const browser=await chromium.launch({channel:'chrome',chromiumSandbox:true})
const contexts=[]
const button=(p,name)=>p.getByRole('button',{name,exact:true})
const link=(p,name)=>p.getByRole('link',{name,exact:true})
const label=(p,name)=>p.getByLabel(name,{exact:true})
const shown=l=>l.waitFor({state:'visible',timeout:10000})
const text=(p,s)=>p.getByText(s,{exact:true})
async function context(){const c=await browser.newContext({locale:'zh-CN',viewport:{width:1280,height:800}});c.setDefaultTimeout(10000);await c.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());contexts.push(c);return c}
async function login(p,portal,user){await p.goto(origin+'/'+portal+'/login');await label(p,'账号').fill(user);await label(p,'密码').fill(credentials[user]);await button(p,portal==='shop'?'进入客服':'进入工作台').click();await shown(button(p,'退出'))}
async function say(p,s){await shown(label(p,'咨询内容'));await p.waitForFunction(()=>!document.querySelector('.handoff-link')?.disabled);await label(p,'咨询内容').fill(s);await button(p,'发送').click();await shown(text(p,s))}
async function hub(p){await link(p,'订单与售后').click();await shown(p.getByRole('heading',{name:'订单与售后',exact:true}));await p.locator('.el-loading-mask').waitFor({state:'hidden'})}
async function open(p,id){await p.locator(`a[href$="/tickets/${id}"]`).first().click();await shown(p.getByRole('heading',{name:new RegExp('^(工单|售后进度) #'+id+'$')}));await p.locator('.el-loading-mask').waitFor({state:'hidden'})}
async function stage(name,fn){await fn();checks.push(name);console.log('通过  '+name)}
const customer=await (await context()).newPage(), staff=await (await context()).newPage()
const message=(p,s)=>p.locator('.ticket-message-log').getByText(s,{exact:true})
const draftA='您好，已看到按键失灵的说明，我正在核对订单。'
const privateNote='内部核查：本地演示订单，仅供客服查阅。'
const decision='请先更换连接线并重启设备。如仍失灵，请反馈具体按键。'
const feedback='换过连接线，A 键仍然没有反应，请继续核查。'
let firstPath
try {
 await stage('人工提交直接进入售后，客服待办仅列本人可处理工单',async()=>{
  await login(customer,'shop','demo_user')
  await button(customer,'申请退款').click();await customer.locator('.wx-order-card').filter({hasText:'机械键盘套件'}).click();await button(customer,'填写退款申请').click();await label(customer,'退款原因').fill('A 键没有反应');await button(customer,'确认提交申请').click();await shown(customer.getByRole('heading',{name:'售后进度 #1'}));firstPath=new URL(customer.url()).pathname
  for(const issue of ['我忘记登录密码了','密码重置后无法登录']){await link(customer,'咨询客服').click();await say(customer,issue);await button(customer,'人工').click();await shown(customer.getByRole('dialog',{name:'提交给人工客服'}));await button(customer,'确认提交人工').click();await shown(customer.getByRole('heading',{name:/^售后进度 #/}))}
  await hub(customer);assert.equal(await customer.getByRole('link',{name:/^#\d+ /}).count(),3);await open(customer,1)
  await login(staff,'staff','demo_agent');await shown(staff.locator('a[href="/staff/tickets/1"]'));assert.equal(await staff.locator('a[href="/staff/tickets/2"]').count(),0);await open(staff,1)
  assert.match(await staff.locator('.request-brief').innerText(),/A 键没有反应/);assert.match(await staff.locator('.order-facts').innerText(),/299.00/)
  await button(staff,'接单并开始处理').click();await shown(customer.locator('.ticket-hero .status-badge').filter({hasText:'处理中'}))
 })
 await stage('公开回复、内部备注、审核草稿按工单隔离，切单返回可续写',async()=>{
  await label(staff,'公开回复').fill(draftA);await button(staff,'写内部备注').click();await label(staff,'内部备注').fill(privateNote)
  await button(staff,'提交处理结果').click();await label(staff,'审核结论').selectOption('declined');await label(staff,'给顾客的处理意见').fill(decision)
  await open(staff,3);await button(staff,'接单并开始处理').click();await label(staff,'公开回复').fill('这是账号单的独立草稿')
  await open(staff,1);assert.equal(await label(staff,'给顾客的处理意见').inputValue(),decision);assert.equal(await label(staff,'审核结论').inputValue(),'declined')
  await staff.setViewportSize({width:1280,height:720})
  const box=await button(staff,'发送处理结果').boundingBox();assert.ok(box.y+box.height<=720,'发送处理结果按钮应在桌面可视区')
  assert.ok(await button(staff,'发送处理结果').evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height-2))}),'发送按钮不能被父容器裁切')
  assert.ok(await staff.locator('.ticket-message-log').evaluate(e=>e.clientHeight)>=50,'写结果时沟通区不能被挤没')
  await staff.screenshot({path:join(output,'staff-draft-restored.png')})
  await button(staff,'写内部备注').click();assert.equal(await label(staff,'内部备注').inputValue(),privateNote)
  await button(staff,'保存内部备注').click();await shown(message(staff,privateNote));await button(staff,'回复顾客').click();assert.equal(await label(staff,'公开回复').inputValue(),draftA)
 })
 await stage('顾客停留页面自动收到客服回复，正在写的内容不丢失且内部备注不泄露',async()=>{
  await label(customer,'公开回复').fill('补充：不是所有按键都失灵')
  let navigations=0;const track=()=>{navigations++};customer.on('framenavigated',track)
  await button(staff,'发送回复').click();await shown(message(customer,draftA));await shown(text(customer,'收到客服的新回复'))
  assert.equal(navigations,0);customer.off('framenavigated',track)
  assert.equal(await label(customer,'公开回复').inputValue(),'补充：不是所有按键都失灵');assert.ok(!(await customer.locator('body').innerText()).includes(privateNote))
  await customer.screenshot({path:join(output,'customer-live-reply.png')})
  await button(customer,'发送回复').click();await shown(message(staff,'补充：不是所有按键都失灵'))
  await button(staff,'提交处理结果').click();assert.equal(await label(staff,'给顾客的处理意见').inputValue(),decision)
  assert.equal(await button(staff,'发送处理结果').isEnabled(),false)
  assert.ok(await label(staff,'给顾客的处理意见').evaluate(e=>{const r=e.getBoundingClientRect();return document.elementFromPoint(r.x+8,r.y+r.height-5)===e}),'核对新消息时仍应完整显示处理意见输入框')
  await staff.screenshot({path:join(output,'staff-review-update.png')})
  await button(staff,'已核对最新内容').click();await button(staff,'发送处理结果').click();await shown(button(customer,'问题还没解决'))
 })
 await stage('未解决反馈原子重开原单，客服自动收到补充并继续处理',async()=>{
  await button(customer,'问题还没解决').click();await label(customer,'仍需帮助的问题').fill(feedback);await button(customer,'发送并继续处理').click();await shown(text(customer,'补充已发送，客服将继续处理这张售后单。'))
  assert.equal(new URL(customer.url()).pathname,firstPath);await shown(message(staff,feedback));await shown(button(staff,'接单并开始处理'));await shown(staff.locator('.nearby-cases a').filter({hasText:'#1'}).getByText('顾客有补充 · 待回复',{exact:true}))
  await staff.screenshot({path:join(output,'staff-followup.png')});await button(staff,'接单并开始处理').click();await button(staff,'提交处理结果').click();await label(staff,'审核结论').selectOption('approved');await label(staff,'给顾客的处理意见').fill('已收到复测说明，同意退款申请。此处记录审核结果，实际到账需另行核对。');await button(staff,'发送处理结果').click()
  await shown(customer.getByRole('heading',{name:'审核通过'}));await shown(button(customer,'确认结束本次服务'));await button(customer,'确认结束本次服务').click();await shown(text(customer,'已关闭'));await customer.reload();await shown(text(customer,'已关闭'))
  await hub(customer);assert.equal(await customer.getByRole('link',{name:/^#\d+ /}).count(),3)
 })
 await stage('手机先显示处理意见和沟通，完整进度可展开；断连保留草稿并恢复更新',async()=>{
  await customer.setViewportSize({width:390,height:844});await open(customer,1);await customer.reload();await shown(text(customer,'已关闭'))
  assert.ok(await customer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
  const layout=await customer.evaluate(()=>({reply:document.querySelector('.latest-response').getBoundingClientRect().top,conversation:document.querySelector('.conversation-panel').getBoundingClientRect().top,history:document.querySelector('.customer-progress').getBoundingClientRect().top}))
  assert.ok(layout.reply<layout.conversation && layout.conversation<layout.history)
  await customer.screenshot({path:join(output,'customer-mobile-result.png')})
  await button(staff,'下一张待处理').click();await shown(staff.getByRole('heading',{name:'工单 #3'}));assert.equal(await label(staff,'公开回复').inputValue(),'这是账号单的独立草稿')
  await staff.bringToFront();await staff.route('**/api/tickets/3',r=>r.abort());await shown(staff.getByText(/自动更新暂不可用/));assert.equal(await label(staff,'公开回复').inputValue(),'这是账号单的独立草稿')
  await staff.unroute('**/api/tickets/3');await shown(text(staff,'回复与进度自动更新'))
  await button(staff,'退出').click();await login(staff,'staff','demo_agent');await open(staff,3);assert.equal(await label(staff,'公开回复').inputValue(),'')
 })
 writeFileSync(join(output,'result.json'),JSON.stringify({passed:true,browser:browser.version(),checks},null,2))
} catch(e) {
 const message=Object.values(credentials).reduce((s,key)=>s.replaceAll(key,'[隐藏]'),String(e.message));console.error(message)
 await customer.screenshot({path:join(output,'failure-customer.png')}).catch(()=>{});await staff.screenshot({path:join(output,'failure-staff.png')}).catch(()=>{})
 writeFileSync(join(output,'result.json'),JSON.stringify({passed:false,checks,error:message},null,2));process.exitCode=1
} finally {for(const c of contexts)await c.close();await browser.close()}
