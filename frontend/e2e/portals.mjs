// Invoked by scripts/check_portals.py with a new local origin and throwaway accounts.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const { origin, credentials, output } = JSON.parse(readFileSync(0, 'utf8'))
const results = []
const internal = '内部核验：已核对顾客的原话。'
const reply = '已登记，正在核查键盘订单。'
const refund = '#1 我要退款'
const account = '#2 我忘记登录密码了'
const button = (page, name) => page.getByRole('button', { name, exact: true })
const link = (page, name) => page.getByRole('link', { name, exact: true })
const shown = locator => locator.waitFor({ state: 'visible', timeout: 8000 })

async function stage(name, action) {
  await action()
  results.push(name)
  console.log('通过  ' + name)
}

async function login(page, portal, user) {
  await page.goto(origin + '/' + portal + '/login')
  await page.getByLabel('账号', { exact: true }).fill(user)
  await page.getByLabel('密码', { exact: true }).fill(credentials[user])
  await button(page, portal === 'shop' ? '进入客服' : '进入工作台').click()
}

async function wrongLogin(page, portal, user) {
  await login(page, portal, user)
  await shown(page.getByText(portal === 'shop' ? /这是顾客入口/ : /这是员工入口/))
  await page.reload()
  await shown(page.getByLabel('账号', { exact: true }))
  assert.equal(new URL(page.url()).pathname, '/' + portal + '/login')
  assert.equal((await page.request.get(origin + '/api/auth/me')).status(), 401)
}

async function say(page, text) {
  await page.getByLabel('咨询内容').fill(text)
  await button(page, '发送').click()
  await shown(page.getByText(text, { exact: true }))
}

async function submitHandoff(page) {
  await button(page, '确认提交人工').click()
  await shown(page.getByRole('heading', {name:/^售后进度 #/}))
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
}

async function openHub(page) {
  await link(page, '订单与售后').click()
  await shown(page.getByRole('heading', { name: '订单与售后', exact: true }))
}

async function verifyChatLayout(page) {
  await page.waitForFunction(() => Math.abs(
    document.querySelector('.support-consulting').getBoundingClientRect().height - window.visualViewport.height,
  ) < 2)
  const layout = await page.evaluate(() => {
    const box = selector => document.querySelector(selector).getBoundingClientRect()
    const chat = box('.wx-chat')
    const footer = box('.wx-footer')
    const input = box('#support-draft')
    const nav = box('.shop-top')
    return {
      height: window.visualViewport.height,
      pageHeight: document.documentElement.scrollHeight,
      pageWidth: document.documentElement.scrollWidth,
      width: innerWidth,
      chatTop: chat.top,
      chatBottom: chat.bottom,
      footerBottom: footer.bottom,
      inputBottom: input.bottom,
      navBottom: nav.bottom,
    }
  })
  assert.ok(layout.pageWidth <= layout.width, '咨询页不应整页横向溢出')
  assert.ok(layout.pageHeight <= layout.height + 2, '咨询页应由会话内容内部滚动 ' + JSON.stringify(layout))
  assert.ok(layout.chatTop >= layout.navBottom, '咨询窗口不得遮挡顶部导航')
  assert.ok(layout.height - layout.chatBottom <= 24, '客服窗口应延伸到可用区域底部')
  assert.ok(layout.footerBottom <= layout.height, '输入区应留在可见区域')
  assert.ok(layout.inputBottom <= layout.footerBottom, '输入框应完整显示')
  assert.equal(await link(page, '订单与售后').count(), 1)
  assert.equal(await page.locator('.support-workspace a[href^="/shop/orders"]').count(), 0)
}

async function localContext(browser, options) {
  const context = await browser.newContext(options)
  // Local acceptance must not wait on third-party font downloads.
  await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, request => request.abort())
  return context
}

async function verify(browser) {
  const shop = await localContext(browser, { locale: 'zh-CN' })
  const staff = await localContext(browser, { locale: 'zh-CN' })
  shop.setDefaultTimeout(8000)
  staff.setDefaultTimeout(8000)
  const customer = await shop.newPage()
  const agent = await staff.newPage()
  await stage('两个门户均拒绝错误角色，刷新后身份接口返回 401', async () => {
    await wrongLogin(customer, 'shop', 'demo_agent')
    await wrongLogin(agent, 'staff', 'demo_user')
  })
  await login(customer, 'shop', 'demo_user')
  await stage('退款政策走知识库，退款中的订单查物流按记录答复，顾客可自行结束', async () => {
    await shown(customer.getByRole('heading', { name: '需要办理什么？' }))
    assert.equal(await customer.locator('.wx-order-card').count(), 0)
    assert.equal(await customer.getByText('机械键盘套件', {exact:true}).count(), 0)
    await customer.mouse.move(1, 1)
    await verifyChatLayout(customer)
    await customer.screenshot({path:join(output, 'service-desktop.png'), animations:'disabled'})
    await customer.setViewportSize({width:390,height:844})
    await customer.reload()
    await shown(customer.getByLabel('咨询内容'))
    await verifyChatLayout(customer)
    await customer.screenshot({path:join(output, 'service-mobile.png'), animations:'disabled'})
    assert.ok(await customer.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await customer.setViewportSize({width:390,height:480})
    await customer.getByLabel('咨询内容').focus()
    await verifyChatLayout(customer)
    await customer.setViewportSize({width:390,height:844})
    await link(customer, '订单与售后').click()
    await button(customer, '我的订单').click()
    const purchases = customer.getByRole('region', {name:'我的订单'}).getByRole('article')
    await shown(purchases.last())
    assert.equal(await purchases.count(), 3)
    await customer.reload()
    await shown(purchases.last())
    await purchases.locator('img').evaluateAll(images => Promise.all(images.map(image => image.decode())))
    await customer.locator('.el-loading-mask').waitFor({state:'hidden'})
    await customer.screenshot({path:join(output, 'orders-mobile.png'), animations:'disabled'})
    await purchases.filter({hasText:'无线蓝牙耳机'}).getByRole('link', {name:'咨询这笔订单'}).click()
    await shown(customer.getByText(/已选：无线蓝牙耳机/))
    await button(customer, '更换').click()
    await customer.locator('.wx-order-card').filter({hasText:'保温杯'}).click()
    await shown(customer.getByText(/已选：保温杯/))
    await customer.reload()
    await shown(customer.getByText(/已选：保温杯/))
    await button(customer, '重新咨询').click()
    await shown(customer.getByRole('heading', { name: '需要办理什么？' }))
    await customer.setViewportSize({width:1280,height:800})
    const input = customer.getByLabel('咨询内容')
    await input.fill('退款')
    await input.dispatchEvent('keydown', {key:'Enter', isComposing:true})
    assert.equal(await input.inputValue(), '退款')
    await shown(customer.getByRole('heading', { name: '需要办理什么？' }))
    await say(customer, '退款政策是什么')
    await shown(customer.getByText(/待付款、已取消或已退款/))
    assert.equal(await customer.locator('.wx-order-card').count(), 0)
    await button(customer, '关联订单').click()
    await customer.locator('.wx-order-card').filter({hasText:'机械键盘套件'}).click()
    await say(customer, '查询这笔订单的物流')
    await shown(customer.getByText(/当前记录没有可核实的发货进度/))
    await verifyChatLayout(customer)
    await customer.screenshot({path:join(output, 'service-chat.png'), animations:'disabled'})
    await customer.setViewportSize({width:390,height:640})
    await verifyChatLayout(customer)
    await customer.waitForFunction(() => {
      const log = document.querySelector('.wx-log')
      return log.scrollHeight - log.scrollTop - log.clientHeight < 3
    })
    await customer.screenshot({path:join(output, 'service-chat-mobile.png'), animations:'disabled'})
    await customer.locator('.wx-log').evaluate(log => { log.scrollTop = 0 })
    await customer.waitForFunction(() => document.querySelector('.wx-log').scrollTop === 0)
    await customer.setViewportSize({width:390,height:480})
    await verifyChatLayout(customer)
    assert.equal(await customer.locator('.wx-log').evaluate(log => log.scrollTop), 0, '翻看旧消息时应保留阅读位置')
    await customer.setViewportSize({width:1440,height:1000})
    await verifyChatLayout(customer)
    await customer.setViewportSize({width:1280,height:800})
    await button(customer, '问题已解决').click()
    await shown(customer.getByText('已结束', { exact: true }))
    await button(customer, '重新咨询').click()
    await shown(customer.getByText('在线', { exact: true }))
  })
  const lines = ['查物流', '快递没有到', '不是催单，我要退款']
  await stage('顾客改口后用文字要求转人工，预览仍为最新诉求，取消不建单', async () => {
    for (const text of lines) await say(customer, text)
    await customer.locator('.wx-order-card').filter({hasText:'机械键盘套件'}).click()
    await say(customer, '帮我转人工')
    const dialog = customer.getByRole('dialog')
    await shown(dialog)
    assert.match(await dialog.innerText(), /当前诉求：\s*我要退款/)
    assert.match(await dialog.innerText(), /机械键盘套件/)
    await button(customer, '取消').click()
    await dialog.waitFor({ state: 'hidden' })
    await openHub(customer)
    await shown(customer.getByText('暂无售后记录', { exact: true }))
  })
  await stage('确认后仅生成一张退款单，未关联订单的账号问题也能转单', async () => {
    await link(customer, '咨询客服').click()
    await button(customer, '人工').click()
    await submitHandoff(customer)
    await openHub(customer)
    await shown(link(customer, refund))
    assert.equal(await customer.getByRole('link', { name: /^#\d+ / }).count(), 1)
    await link(customer, '咨询客服').click()
    await say(customer, '我忘记登录密码了')
    await button(customer, '人工').click()
    assert.match(await customer.getByRole('dialog').innerText(), /未关联订单/)
    await submitHandoff(customer)
    await button(customer, '退出').click()
    await shown(button(customer, '进入客服'))
    await shop.close()
  })
  await stage('客服收到退款分类和顾客原话，接单、分别回复并标记解决', async () => {
    await login(agent, 'staff', 'demo_agent')
    await shown(link(agent, refund))
    await agent.locator('.el-loading-mask').waitFor({state:'hidden'})
    await agent.screenshot({path:join(output,'staff-queue.png'), animations:'disabled'})
    assert.match(await agent.getByRole('row').filter({ has: link(agent, refund) }).innerText(), /退款咨询/)
    await link(agent, refund).click()
    await agent.getByText(/查看顾客原话/).click()
    const statements = await agent.locator('details').filter({hasText:'查看顾客原话'}).locator('ol li').allTextContents()
    assert.deepEqual(statements, [...lines, '帮我转人工'])
    await button(agent, '接单并开始处理').click()
    await shown(agent.getByText('处理中', { exact: true }))
    await button(agent, '写内部备注').click()
    await agent.getByLabel('内部备注', { exact: true }).fill(internal)
    await button(agent, '保存内部备注').click()
    await shown(agent.getByText(internal, { exact: true }))
    await button(agent, '回复顾客').click()
    await agent.getByLabel('公开回复', { exact: true }).fill(reply)
    await button(agent, '发送回复').click()
    await shown(agent.getByText(reply, { exact: true }))
    await shown(agent.getByText('处理中', {exact:true}))
    await button(agent, '提交处理结果').click()
    assert.equal(await button(agent, '发送处理结果').isEnabled(),false)
    await agent.getByLabel('审核结论').selectOption('approved')
    await agent.getByLabel('给顾客的处理意见').fill('已核对商品问题，同意本次退款申请；实际到账需另行核对。')
    await agent.getByText(/查看顾客原话/).click()
    await agent.evaluate(() => window.scrollTo(0, 0))
    await agent.screenshot({path:join(output, 'staff-refund.png'),fullPage:true})
    await button(agent, '发送处理结果').click()
    await shown(agent.getByText('待确认', { exact: true }))
  })
  await stage('顾客重新登录后能查到两张单，只见公开回复，确认关闭后刷新仍有效', async () => {
    const fresh = await localContext(browser, { locale: 'zh-CN' })
    fresh.setDefaultTimeout(8000)
    const page = await fresh.newPage()
    await login(page, 'shop', 'demo_user')
    const recentCase = page.getByRole('link', {name:/进行中的售后/})
    await shown(recentCase)
    assert.match(await recentCase.innerText(), /审核通过 · 待确认/)
    await page.mouse.move(1, 1)
    await page.screenshot({path:join(output, 'service-return.png'), animations:'disabled'})
    await recentCase.click()
    await shown(page.getByRole('heading', {name:'售后进度 #1'}))
    await openHub(page)
    await shown(link(page, account))
    assert.match(await page.getByRole('listitem').filter({ has: link(page, account) }).innerText(), /未关联订单/)
    await link(page, account).click()
    await shown(page.getByRole('heading', { name: '售后进度 #2' }))
    await openHub(page)
    await link(page, refund).click()
    await shown(page.locator('.ticket-message-log').getByText(reply, { exact: true }))
    await shown(page.getByRole('heading', {name:'审核通过'}))
    await page.setViewportSize({width:390,height:844})
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({path:join(output,'customer-review-mobile.png'), animations:'disabled'})
    await page.setViewportSize({width:1280,height:720})
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    await page.screenshot({path:join(output, 'customer-review.png')})
    assert.doesNotMatch(await page.locator('body').innerText(), /内部核验|内部备注/)
    await button(page, '确认结束本次服务').click()
    await shown(page.getByText('已关闭', { exact: true }))
    await page.reload()
    await shown(page.getByText('已关闭', { exact: true }))
    await shown(page.locator('.ticket-message-log').getByText(reply, { exact: true }))
    await page.screenshot({ path: join(output, 'customer-closed.png') })
    await openHub(page)
    await shown(link(page, refund))
    assert.match(await page.getByRole('listitem').filter({ has: link(page, refund) }).innerText(), /已关闭/)
    await page.screenshot({ path: join(output, 'aftersales.png') })
  })
  await stage('顾客自助填写退款原因，同一订单重复申请可回原单，查进度不会再建单', async () => {
    const fresh = await localContext(browser, {locale:'zh-CN', viewport:{width:390,height:844}})
    const page = await fresh.newPage()
    await login(page,'shop','demo_user')
    await button(page,'申请退款').click()
    await page.locator('.wx-order-card').filter({hasText:'机械键盘套件'}).click()
    await button(page,'填写退款申请').click()
    await page.getByLabel('退款原因').fill('键盘有几个按键失灵')
    await button(page,'确认提交申请').click()
    await shown(page.getByRole('heading',{name:'等待客服审核'}))
    const href = new URL(page.url()).pathname
    await link(page,'咨询客服').click()
    await shown(page.getByRole('heading',{name:'需要办理什么？'}))
    await say(page,'我想申请退款')
    await page.locator('.wx-order-card').filter({hasText:'机械键盘套件'}).click()
    const original = page.getByRole('link',{name:/查看退款申请 #/})
    await shown(original)
    assert.equal(await original.getAttribute('href'), href)
    await say(page,'钱什么时候能退回来')
    await shown(page.getByText(/等待客服审核。打开售后单/))
    await original.click()
    await shown(page.getByRole('heading',{name:'等待客服审核'}))
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await fresh.close()
  })
}

let browser
try {
  browser = await chromium.launch({ channel: 'chrome', chromiumSandbox: true })
  await verify(browser)
  writeFileSync(join(output, 'result.json'), JSON.stringify({ passed: true, browser: browser.version(), checks: results }, null, 2))
} catch (error) {
  const message = String(error.message)
  const sanitized = Object.values(credentials).reduce((text, secret) => text.replaceAll(secret, '[隐藏]'), message)
  writeFileSync(join(output, 'result.json'), JSON.stringify({ passed: false, checks: results, error: sanitized }, null, 2))
  console.error(sanitized)
  process.exitCode = 1
} finally {
  await browser?.close()
}
