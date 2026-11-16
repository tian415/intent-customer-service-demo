// Visible, isolated browser sessions for the local hands-on demo.
import { readFile } from 'node:fs/promises'
import { setTimeout as wait } from 'node:timers/promises'
import { chromium } from 'playwright-core'

const [, , origin, file] = process.argv
if (!/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(origin)) throw Error('只可打开本机体验服务')
const accounts = JSON.parse(await readFile(file, 'utf8'))
const browser = await chromium.launch({ channel: 'chrome', headless: false, chromiumSandbox: true })
try {
  for (let i = 0; i < 50; i++) {
    if (await fetch(origin + '/api/health').then(r => r.ok).catch(() => false)) break
    await wait(200)
  }
  for (const [user, portal, home] of [
    ['demo_admin', 'staff', '/staff/admin/stats'], ['demo_agent', 'staff', '/staff/tickets'],
    ['demo_user', 'shop', '/shop'],
  ]) {
    const ctx = await browser.newContext({ locale: 'zh-CN', viewport: null })
    const page = await ctx.newPage()
    await page.goto(origin + '/' + portal + '/login')
    await page.getByLabel('账号', { exact: true }).fill(user)
    await page.getByLabel('密码', { exact: true }).fill(accounts[user])
    await page.getByRole('button', { name: portal === 'shop' ? '进入客服' : '进入工作台', exact: true }).click()
    await page.waitForURL(origin + home)
    await page.bringToFront()
    console.log(user + ' 已进入 ' + home)
  }
  await new Promise(resolve => browser.once('disconnected', resolve))
} finally {
  await browser.close()
}
