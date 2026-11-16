ALTER TABLE tickets ADD COLUMN refund_stage TEXT CHECK(refund_stage IN ('requested','approved','declined'));
CREATE UNIQUE INDEX tickets_one_open_refund ON tickets(owner_id, order_id) WHERE refund_stage IS NOT NULL AND status <> 'closed';
UPDATE faqs SET answer = '本店接受本人已付款订单的退款申请。待付款、已取消或已退款的订单不能新申请。是否符合退款条件由客服根据原因审核。申请时请选本人订单，填写退款原因并确认提交。客服审核后会在「我的售后」留下处理意见；提交申请不会直接产生退款。' WHERE question = 'DEMO：如何咨询退款？' AND answer = 'DEMO 演示知识：请提交工单说明问题，由客服人工核实。请勿填写银行卡或其他敏感信息。';
