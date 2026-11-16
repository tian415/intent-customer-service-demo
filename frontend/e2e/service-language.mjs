// Engineering regression only; generated cases are not independent language evaluation.
import assert from 'node:assert/strict'
import {readFileSync, writeFileSync} from 'node:fs'
import {join} from 'node:path'
import {chromium} from 'playwright-core'

const {origin, credentials, output} = JSON.parse(readFileSync(0, 'utf8'))
const browser = await chromium.launch({channel:'chrome', chromiumSandbox:true})
const contexts = [], checks = []
const button = (p,s) => p.getByRole('button', {name:s, exact:true})
const link = (p,s) => p.getByRole('link', {name:s, exact:true})
const label = (p,s) => p.getByLabel(s, {exact:true})
const shown = l => l.waitFor({state:'visible', timeout:10000})
async function page() {
 const c = await browser.newContext({locale:'zh-CN', viewport:{width:1280,height:800}})
 c.setDefaultTimeout(10000)
 await c.route('**/*', r => new URL(r.request().url()).origin === origin ? r.continue() : r.abort())
 contexts.push(c); return c.newPage()
}
async function login(p, portal, user) {
 await p.goto(origin+'/'+portal+'/login'); await label(p,'账号').fill(user); await label(p,'密码').fill(credentials[user])
 await button(p, portal==='shop'?'进入客服':'进入工作台').click(); await shown(button(p,'退出'))
}
async function say(p,s) {
 await p.waitForFunction(()=>!document.querySelector('.handoff-link')?.disabled)
 await label(p,'咨询内容').fill(s); await button(p,'发送').click()
 await shown(p.locator('.chat-bubble[data-role="user"]').getByText(s,{exact:true}))
 await p.waitForFunction(()=>document.querySelector('#support-draft')?.value==='')
}
async function reply(p,s) {await shown(p.locator('.chat-bubble[data-role="assistant"]').last().filter({hasText:s}))}
async function fresh(p) {await button(p,'重新咨询').click(); await shown(p.getByRole('heading',{name:'需要办理什么？'}))}
async function stage(name, fn) {await fn(); checks.push(name); console.log('通过  '+name)}
async function dismissRefresh(p) {
 const started = await p.evaluate(()=>performance.timeOrigin)
 const session = await p.context().newCDPSession(p)
 try {
  const event = p.waitForEvent('dialog'); const reload = session.send('Page.reload')
  const dialog = await event; assert.equal(dialog.type(),'beforeunload'); await dialog.dismiss(); await reload
  assert.equal(await p.evaluate(()=>performance.timeOrigin),started,'取消刷新后仍应是原页面')
 } finally {await session.detach()}
}
async function cancelConfirm(p, action) {
 const event = p.waitForEvent('dialog'); const click = action()
 const dialog = await event; assert.equal(dialog.type(),'confirm'); await dialog.dismiss(); await click
}
const customer = await page(), staff = await page()
try {
 await stage('口语退款规则、拒绝办理、退款换货二选一和到账追问正确分流',async()=>{
  await login(customer,'shop','demo_user')
  await say(customer,'不合适的话能退不？'); await reply(customer,'本店接受本人已付款订单')
  await say(customer,'我要退款'); await customer.locator('.wx-order-card').filter({hasText:'机械键盘套件'}).click(); await shown(button(customer,'填写退款申请'))
  await say(customer,'别给我退款'); await reply(customer,'原诉求不再办理'); assert.equal(await button(customer,'填写退款申请').count(),0)
  await say(customer,'我想退货或者换货，哪个好'); await reply(customer,'换货'); assert.equal(await button(customer,'填写退款申请').count(),0)
  await say(customer,'查退款进度'); await say(customer,'那什么时候能到账'); await reply(customer,'到账记录')
  await say(customer,'这单在退款，但我现在问的是快递发货了吗'); await reply(customer,'没有可核实的发货进度')
  await say(customer,'能保证明天送到吗'); await reply(customer,'无法保证具体送达日期')
  await customer.screenshot({path:join(output,'customer-context.png')})
 })
 await stage('登录问题先澄清，验证码失败交接人工后保留原话，不误答重置密码',async()=>{
  await fresh(customer); await say(customer,'我的帐号进不去了'); await reply(customer,'收不到验证码')
  await say(customer,'不是忘记密码，是一直收不到验证码'); await reply(customer,'无法核实验证码')
  await button(customer,'人工').click(); await shown(customer.getByRole('dialog',{name:'提交给人工客服'}))
  await button(customer,'确认提交人工').click(); await shown(customer.getByRole('heading',{name:'售后进度 #1'}))
  await login(staff,'staff','demo_agent'); await staff.goto(origin+'/staff/tickets/1'); await shown(button(staff,'接单并开始处理'))
  await staff.locator('summary').filter({hasText:'查看顾客原话'}).click()
  const brief = await staff.locator('.ticket-hero').innerText(); assert.match(brief,/我的帐号进不去了/); assert.match(brief,/一直收不到验证码/)
  await button(staff,'接单并开始处理').click(); await shown(label(staff,'公开回复'))
 })
 await stage('客服离开工单仍保护其他单的未发草稿，取消刷新可续写，发送后正常刷新',async()=>{
  const draft = '请补充登录页面的错误提示，不要提供密码或验证码。'
  await label(staff,'公开回复').fill(draft); await link(staff,'工单台').click()
  await dismissRefresh(staff)
  await staff.locator('a[href="/staff/tickets/1"]').first().click(); await shown(label(staff,'公开回复'))
  assert.equal(await label(staff,'公开回复').inputValue(),draft)
  await staff.bringToFront(); await staff.setViewportSize({width:1280,height:720})
  await staff.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))
  const sendBox=await button(staff,'发送回复').boundingBox(); assert.ok(sendBox.y>=0 && sendBox.y+sendBox.height<=720)
  assert.ok(await button(staff,'发送回复').evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}))
  await staff.screenshot({path:join(output,'staff-draft-protected.png')})
  await button(staff,'发送回复').click(); await shown(staff.locator('.ticket-message-log').getByText(draft,{exact:true}))
  await customer.bringToFront(); await shown(customer.locator('.ticket-message-log').getByText(draft,{exact:true}))
  await staff.reload(); await shown(staff.getByRole('heading',{name:'工单 #1'}))
 })
 await stage('耳机口语排查失败保留症状与反馈，客服接单回复到达顾客手机页',async()=>{
  await customer.setViewportSize({width:390,height:844}); await link(customer,'咨询客服').click()
  await say(customer,'耳机左侧没声'); await reply(customer,'左右声道')
  await say(customer,'照你说的试过了，还是听不到'); await reply(customer,'排查后仍然无声')
  await customer.screenshot({path:join(output,'customer-mobile-troubleshooting.png')})
  await button(customer,'人工').click(); await button(customer,'确认提交人工').click(); await shown(customer.getByRole('heading',{name:'售后进度 #2'}))
  await staff.goto(origin+'/staff/tickets/2'); await shown(button(staff,'接单并开始处理'))
  await staff.locator('summary').filter({hasText:'查看顾客原话'}).click()
  const brief = await staff.locator('.ticket-hero').innerText(); assert.match(brief,/耳机左侧没声/); assert.match(brief,/照你说的试过了，还是听不到/)
  await button(staff,'接单并开始处理').click(); await label(staff,'公开回复').fill('已看到排查反馈，请补充是否在另一台设备上也出现左侧无声。'); await button(staff,'发送回复').click()
  await customer.bringToFront(); await shown(customer.locator('.ticket-message-log').getByText('已看到排查反馈，请补充是否在另一台设备上也出现左侧无声。',{exact:true}))
 })
 await stage('口语恢复结束咨询；顾客取消离开、重新咨询和刷新都保留未发文字',async()=>{
  await link(customer,'咨询客服').click(); await say(customer,'耳机左侧没声'); await say(customer,'好了，现在能听到了')
  await reply(customer,'结束本次咨询'); assert.ok(await label(customer,'咨询内容').isDisabled()); await fresh(customer)
  await say(customer,'退款规则是什么'); const draft='我还想补充一下具体情况'; await label(customer,'咨询内容').fill(draft)
  await cancelConfirm(customer,()=>link(customer,'订单与售后').click()); assert.equal(await label(customer,'咨询内容').inputValue(),draft)
  await cancelConfirm(customer,()=>button(customer,'重新咨询').click()); assert.equal(await label(customer,'咨询内容').inputValue(),draft)
  await dismissRefresh(customer); assert.equal(await label(customer,'咨询内容').inputValue(),draft)
  await customer.setViewportSize({width:390,height:500})
  await customer.waitForFunction(()=>document.querySelector('.support-consulting')?.getBoundingClientRect().height===innerHeight)
  await customer.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))
  const box=await button(customer,'发送').boundingBox(); assert.ok(box.y>=0 && box.y+box.height<=500)
  assert.ok(await customer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
  await customer.screenshot({path:join(output,'customer-short-viewport.png')})
  const event=customer.waitForEvent('dialog'); const click=link(customer,'订单与售后').click(); await (await event).accept(); await click
  await shown(customer.getByRole('heading',{name:'订单与售后',exact:true})); await link(customer,'咨询客服').click(); assert.equal(await label(customer,'咨询内容').inputValue(),'')
 })
 writeFileSync(join(output,'result.json'),JSON.stringify({passed:true,browser:browser.version(),checks,mobile:'Emulated viewport; no physical phone keyboard tested'},null,2))
} catch(e) {
 const message=Object.values(credentials).reduce((s,key)=>s.replaceAll(key,'[隐藏]'),String(e.stack))
 console.error(message); await customer.screenshot({path:join(output,'failure-customer.png')}).catch(()=>{}); await staff.screenshot({path:join(output,'failure-staff.png')}).catch(()=>{})
 writeFileSync(join(output,'result.json'),JSON.stringify({passed:false,checks,error:message},null,2)); process.exitCode=1
} finally {for(const c of contexts)await c.close(); await browser.close()}
