# 基于意图识别的智能客服工单管理系统

一个在本机运行的中文客服演示。顾客可以问物流、查退款或转人工；客服处理申请，管理员查看同一张工单的进度。演示订单和顾客对话均为虚构数据。

## 本机启动

准备 Python 3.12、uv、Node.js 24、npm 10+ 和桌面 Google Chrome。[下载源码 ZIP](https://github.com/tian415/intent-customer-service-demo/archive/refs/heads/main.zip)，解压后在项目目录打开终端。以下命令已在 macOS Apple Silicon 验证。

```sh
(cd backend && uv sync --frozen --group ml)
(cd frontend && npm ci)
backend/.venv/bin/python scripts/try_roles.py --open
```

## 演示一笔退款

启动后会打开三个已登录的窗口。

1. **顾客**在「订单与售后 → 我的订单」选保温杯，点「咨询这笔订单」。可以先问“原因写完就算提交了吗？”，再说“请帮我办理退款”。填写原因并点「确认提交申请」后，页面会显示售后单号。
2. **客服**从待接单队列打开同一张单，接单、填写审核意见，发送处理结果。
3. **顾客**在详情页确认结束服务，**管理员**刷新「运行统计」，查看已关闭工单数。

[操作说明、截图与复验命令](docs/DEMO_GUIDE.md)
