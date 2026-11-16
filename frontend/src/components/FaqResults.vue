<script setup lang="ts">
import { ElAlert, ElCollapse, ElCollapseItem, ElEmpty } from 'element-plus'
import type { FaqResult } from '../types'
defineProps<{result:FaqResult}>()
</script>
<template><div><ElAlert :type="result.reliable?'success':'info'" :closable="false" :title="result.reliable?'找到相关知识，请核对是否适合你的问题。':'未找到可靠匹配，可继续创建工单由客服处理。'"/><ElEmpty v-if="!result.items.length" description="暂无匹配知识" :image-size="60"/><ElCollapse><ElCollapseItem v-for="item in result.items" :key="item.id" :title="item.question" :name="item.id"><p class="prose">{{item.answer}}</p><small class="muted">来源：本地知识库 #{{item.id}}</small></ElCollapseItem></ElCollapse></div></template>
