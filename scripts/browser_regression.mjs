// Run only through Codex cua_repl's documented UI APIs; no external browser driver.
// Credentials are random, private, disposable fixture values and are never returned.
export async function runCore({tab, credentials, info, screenshot, created=false}) {
  const checks = []
  const state = async (contains, absent) => {
    const value = await tab.getAXState({emit:false,disableDiffing:true})
    if (contains && !value.includes(contains)) throw new Error('页面未出现预期内容：'+contains)
    if (absent && value.includes(absent)) throw new Error('页面出现应隔离的内容：'+absent)
    return value
  }
  const button = name => tab.playwright.getByRole('button',{name,exact:true})
  const link = name => tab.playwright.getByRole('link',{name,exact:true}).first()
  async function login(account) {
    await state('登录工作台')
    await tab.playwright.getByLabel('账号',{exact:true}).fill(account)
    await tab.playwright.getByLabel('密码',{exact:true}).fill(credentials[account])
    await button('登录').click();await state('退出登录')
  }
  async function logout() {await button('退出登录').click();await state('登录工作台')}
  async function openFirst() {await tab.playwright.getByRole('link',{name:/^#1 /}).click();await state('工单 #1')}
  if (!created) {
    await login('demo_user')
    await link('新建工单').click();await state('问题标题')
    await tab.playwright.getByLabel('问题标题',{exact:true}).fill('DEMO 浏览器密码重置')
    await tab.playwright.getByLabel('问题描述',{exact:true}).fill('忘记密码登录，需要重置账号密码。仅软件工程验证。')
    await button('提交工单').click()
  }
  await state(info.model_sha256.slice(0,12));await state('model')
  checks.push('用户创建工单，真实训练的DEMO模型预测并保存版本')
  await logout();await login('demo_agent');await openFirst()
  await state('credential_reset');await state(info.mapping_sha256.slice(0,12))
  await button('接单并开始处理').click();await state('处理中')
  await button('写内部备注').click()
  await tab.playwright.getByLabel('内部备注',{exact:true}).fill('DEMO_INTERNAL_NOT_VISIBLE')
  await button('保存内部备注').click();await state('DEMO_INTERNAL_NOT_VISIBLE')
  await button('回复顾客').click();await state('公开回复')
  await tab.playwright.getByLabel('公开回复',{exact:true}).fill('DEMO 公开回复：密码问题已核查，请确认。')
  await button('发送回复').click();await state('DEMO 公开回复')
  await tab.playwright.getByLabel('给顾客的处理意见',{exact:true}).fill('账号已恢复，请重新登录。')
  await button('标记已解决').click();await state('待确认')
  checks.push('客服接单、内部备注、公开回复、标记解决')
  await logout();await login('demo_user');await openFirst()
  await state('DEMO 公开回复','DEMO_INTERNAL_NOT_VISIBLE')
  await button('确认解决并关闭').click();await state('已关闭')
  await button('重新打开工单').click();await state('已分配')
  checks.push('用户仅见公开回复，可关闭和重开')
  await logout();await login('demo_admin');await openFirst()
  await tab.playwright.getByRole('combobox',{name:'人工修正分类',exact:true}).click();await state('退款咨询')
  await tab.playwright.getByRole('option',{name:'退款咨询',exact:true}).click()
  await tab.playwright.getByLabel('纠错理由',{exact:true}).fill('DEMO 人工纠错，保留原模型标签和版本')
  await button('保存分类修正').click();await state('credential_reset');await state(info.model_sha256.slice(0,12))
  await link('系统管理').click();await state('人工分类纠错 1');await state('工单总数 1')
  checks.push('管理员纠错、路由更新、原预测追踪及真实统计')
  await screenshot(tab,'core')
  return {checks}
}

export async function runFallback({tab,credentials,screenshot}) {
  const state = async text => {
    const value = await tab.getAXState({emit:false,disableDiffing:true})
    if (!value.includes(text)) throw new Error('页面未出现预期内容：'+text)
    return value
  }
  const button = name => tab.playwright.getByRole('button',{name,exact:true})
  const link = name => tab.playwright.getByRole('link',{name,exact:true}).first()
  await button('退出登录').click();await state('登录工作台')
  await tab.playwright.getByLabel('账号',{exact:true}).fill('demo_user')
  await tab.playwright.getByLabel('密码',{exact:true}).fill(credentials.demo_user)
  await button('登录').click();await state('我的工单')
  await link('新建工单').click();await state('问题标题')
  await tab.playwright.getByLabel('问题标题',{exact:true}).fill('DEMO 密码降级检查')
  await tab.playwright.getByLabel('问题描述',{exact:true}).fill('忘记登录密码，仅检查模型文件不可用后的规则路径。')
  await button('提交工单').click();await state('rules')
  await screenshot(tab,'fallback')
  return {checks:['模型完整性校验失败后，浏览器新工单显示规则来源并继续分配']}
}
