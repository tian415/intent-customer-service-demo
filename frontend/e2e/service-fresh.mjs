// Engineering spot check: text-only customer input via the rendered UI. No API injection.
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const { origin, credentials, output, caseSet } = JSON.parse(readFileSync(0, 'utf8'))
const fixtures = {first:'r20-fresh', final:'r20-final', speech:'r21-speech', 'speech-final':'r21-speech-final'}
const loadCases = name => JSON.parse(readFileSync(new URL('./fixtures/'+name+'.json', import.meta.url)))
const history = Object.values(fixtures)
const complete = [...history, 'r22-fresh', 'r22-acceptance', 'r22-release', 'r22-colloquial', 'r22-final']
const batches = {history, complete}[caseSet] ?? [fixtures[caseSet] ?? caseSet]
const cases = batches.flatMap(loadCases)
assert.equal(new Set(cases.map(c => c.id)).size, cases.length)
const answers = {
  '换配件': /配件|换货|换件|联系人工|确认转接|交给客服/,
  '按钮说明': /填写退款申请.{0,12}打开表单.*退款原因.*确认提交申请.*提交成功.*取消不会建单/s,
  '物流': /这笔订单已签收|没有实时物流轨迹/,
  '退款进度': /退款审核单|银行到账记录/,
  '期限': /未.{0,5}期限|没有.{0,10}期限/,
  '政策': /退款条件由客服|已付款订单/,
  '办理退款': /可以提交退款申请/,
  '耳机排查': /声道平衡/,
  '验证码': /验证码.{0,14}(原因|人工)/,
  '重设密码': /管理员重设/,
  '退款换货澄清': /申请退款，还是希望换货/,
  '撤回': /原诉求不再办理/,
  '撤单协助': /(?:撤销|撤回|取消).{0,35}人工|人工.{0,35}(撤销|撤回|取消)/,
  '确认意愿': /您是先了解退款|还是决定现在申请|还是要新申请退款/,
  '审核时效': /没有可确认的固定审核时长/,
  '到账时效': /无法给出确切的到账时间/,
  '综合时效': /固定审核时长.*确切的到账时间/s,
  '已有申请和到账': /未查到这笔订单的退款审核单.*确切的到账时间/s,
  '已有申请和审核': /未查到这笔订单的退款审核单.*固定审核时长/s,
  '澄清': /具体想查询什么|请补充/,
  '其他款项': /具体想查询什么|请补充|请.*人工|交给客服/,
}
const browser = await chromium.launch({ channel:'chrome', chromiumSandbox:true })
const results = []
try {
  const ctx = await browser.newContext({locale:'zh-CN', viewport:{width:1100,height:820}})
  ctx.setDefaultTimeout(8000)
  const p = await ctx.newPage()
  const button = name => p.getByRole('button', {name, exact:true})
  await p.goto(origin + '/shop/login')
  await p.getByLabel('账号',{exact:true}).fill('demo_user')
  await p.getByLabel('密码',{exact:true}).fill(credentials.demo_user)
  await button('进入客服').click()
  for (const [i, c] of cases.entries()) {
    if (i > 0) await button('重新咨询').click()
    await p.getByRole('heading',{name:'需要办理什么？'}).waitFor()
    if (c.bind !== false) {
      await p.getByRole('link',{name:'订单与售后',exact:true}).click()
      await button('我的订单').click()
      await p.getByRole('article').filter({hasText:'保温杯'}).getByRole('link',{name:'咨询这笔订单'}).click()
      await p.getByText(/已选：保温杯/).waitFor()
    }
    const trace = []
    const states = []
    for (const text of c.steps) {
      await p.getByLabel('咨询内容').fill(text)
      await button('发送').click()
      await p.locator('.chat-bubble[data-role="user"]').getByText(text,{exact:true}).waitFor()
      await p.waitForFunction(() => !document.querySelector('#support-draft').value)
      trace.push(await p.locator('.chat-bubble[data-role="assistant"]').last().innerText())
      states.push({refundButton:await button('填写退款申请').isVisible(),
        pickingOrder:await p.locator('.wx-order-card').first().isVisible()})
    }
    const reply = trace.at(-1)
    const refundButton = await button('填写退款申请').isVisible()
    const matches = (want, index) => {
      const infoOnly = ['审核时效','到账时效','综合时效','确认意愿','按钮说明'].includes(want)
      return answers[want].test(trace[index]) && states[index].refundButton === (want === '办理退款')
        && (!infoOnly || !states[index].pickingOrder && !/未查到这笔订单|退款审核单/.test(trace[index]))
        && (want !== '其他款项' || !/退款审核单|银行到账记录|到账时间|提交退款申请/.test(trace[index]))
    }
    if (c.wants) assert.equal(c.wants.length, c.steps.length)
    const passed = matches(c.want, trace.length - 1) && (!c.wants || c.wants.every(matches))
    results.push({...c, trace, states, refundButton, passed})
    if (!passed || i === 0) await p.screenshot({path:join(output,c.id+'.png')})
    console.log(c.id, passed?'符合预期':'需要复核', reply)
  }
  await p.getByRole('link',{name:'订单与售后',exact:true}).click()
  await button('我的全部售后').click()
  await p.getByText('暂无售后记录',{exact:true}).waitFor()
  assert.equal(results.length,cases.length)
  writeFileSync(join(output,'result.json'),JSON.stringify({browser:browser.version(),results,noTicketCreated:true},null,2)+'\n')
  if (results.some(r=>!r.passed)) process.exitCode=1
} finally {
  await browser.close()
}
