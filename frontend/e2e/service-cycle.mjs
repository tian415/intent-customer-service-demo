import assert from 'node:assert/strict'
import {readFileSync, writeFileSync} from 'node:fs'
import {join} from 'node:path'
import {chromium} from 'playwright-core'

const {origin, credentials, output} = JSON.parse(readFileSync(0, 'utf8'))
const browser = await chromium.launch({channel:'chrome', chromiumSandbox:true})
const button = (p, name) => p.getByRole('button', {name, exact:true})
const link = (p, name) => p.getByRole('link', {name, exact:true})
const checks = []
async function open(portal, user) {
  const ctx = await browser.newContext({locale:'zh-CN', viewport:{width:1280,height:800}})
  const p = await ctx.newPage()
  p.setDefaultTimeout(10000)
  await p.goto(origin+'/'+portal+'/login')
  await p.getByLabel('账号',{exact:true}).fill(user)
  await p.getByLabel('密码',{exact:true}).fill(credentials[user])
  await button(p,portal==='shop'?'进入客服':'进入工作台').click()
  return p
}
async function say(p, text) {
  await p.getByLabel('咨询内容').fill(text)
  await button(p,'发送').click()
  await p.locator('.chat-bubble[data-role="user"]').getByText(text,{exact:true}).waitFor()
}
async function stage(name, fn) { await fn(); checks.push(name); console.log('通过  '+name) }
try {
  const admin = await open('staff','demo_admin')
  const staff = await open('staff','demo_agent')
  const shop = await open('shop','demo_user')
  const question = '杯盖配件怎么保养'
  const answer = '请用温水清洗杯盖，并晾干后再装回。'
  await stage('管理员从运行统计维护知识，顾客在咨询页读到保存的答复',async()=>{
    await admin.waitForURL('**/staff/admin/stats')
    await link(admin,'知识管理').click()
    await button(admin,'新增知识').click()
    await admin.getByLabel('问题',{exact:true}).fill(question)
    await admin.getByLabel('答案',{exact:true}).fill(answer)
    await button(admin,'保存').click()
    await admin.getByText('保存成功',{exact:true}).waitFor()
    await say(shop,question)
    await shop.locator('.chat-bubble[data-role="assistant"]').last().filter({hasText:answer}).waitFor()
    await staff.getByText('当前没有待处理工单',{exact:true}).waitFor()
    await button(staff,'查看待接单队列').click()
  })
  await stage('打开表单、填写原因和取消后，顾客的售后列表仍为空',async()=>{
    await say(shop,'我想办理退款')
    await shop.locator('.wx-order-card').filter({hasText:'保温杯'}).click()
    const history = await shop.context().newPage()
    const ordersUrl = new URL(await link(shop,'订单与售后').getAttribute('href'), origin).href
    async function assertEmpty() {
      await history.goto(ordersUrl)
      await button(history,'我的全部售后').click()
      await history.getByText('暂无售后记录',{exact:true}).waitFor()
    }
    await button(shop,'填写退款申请').click()
    assert.ok(await button(shop,'确认提交申请').isDisabled())
    await assertEmpty()
    await shop.getByLabel('退款原因').fill('先填写，等核对后再确认。')
    await assertEmpty()
    await button(shop,'取消').click()
    await assertEmpty()
    await history.close()
  })
  await stage('顾客最终确认后产生一张退款单，客服看见同一张单并接单',async()=>{
    await button(shop,'填写退款申请').click()
    await shop.getByLabel('退款原因').fill('杯盖密封圈松动，漏水。')
    await button(shop,'确认提交申请').click()
    await shop.getByRole('heading',{name:'售后进度 #1'}).waitFor()
    await staff.locator('a[href="/staff/tickets/1"]').click()
    await staff.locator('.order-facts').filter({hasText:'59.00'}).waitFor()
    await button(staff,'接单并开始处理').click()
    await shop.locator('.ticket-hero .status-badge').filter({hasText:'处理中'}).waitFor()
  })
  await stage('顾客收到审核意见并确认结束，管理员刷新统计看到同一张已关闭工单',async()=>{
    await button(staff,'提交处理结果').click()
    await staff.getByLabel('审核结论').selectOption('approved')
    await staff.getByLabel('给顾客的处理意见').fill('已核对杯盖漏水情况，同意退款申请。')
    await button(staff,'发送处理结果').click()
    await shop.getByRole('heading',{name:'审核通过'}).waitFor()
    await button(shop,'确认结束本次服务').click()
    await shop.locator('.ticket-hero .status-badge').filter({hasText:'已关闭'}).waitFor()
    await link(admin,'运行统计').click()
    await button(admin,'刷新数据').click()
    await admin.locator('.chart-row').filter({hasText:'已关闭'}).waitFor()
    assert.equal(await admin.locator('.stat').filter({hasText:'工单总数'}).locator('strong').innerText(),'1')
    await admin.waitForFunction(() => !Array.from(document.querySelectorAll('.el-loading-mask')).some(mask => mask.getBoundingClientRect().height > 0))
    for (const width of [1280,390]) {
      await admin.setViewportSize({width,height:820})
      const layout = await admin.evaluate(() => {
        const rect = selector => document.querySelector(selector).getBoundingClientRect()
        return {headerBottom:rect('.admin-page h1').bottom, tabsTop:rect('.admin-tabs').top,
          tabsBottom:rect('.admin-tabs').bottom, statsTop:rect('.stats-grid').top,
          statWidth:rect('.stat').width, docWidth:document.documentElement.scrollWidth}
      })
      assert.ok(layout.headerBottom <= layout.tabsTop && layout.tabsBottom <= layout.statsTop)
      assert.ok(layout.docWidth <= width && layout.statWidth >= (width > 600 ? 180 : 80))
      await admin.screenshot({path:join(output,'admin-'+width+'.png')})
    }
    await shop.screenshot({path:join(output,'customer.png')})
    await staff.screenshot({path:join(output,'staff.png')})
  })
  writeFileSync(join(output,'result.json'),JSON.stringify({browser:browser.version(),checks},null,2)+'\n')
} finally { await browser.close() }
