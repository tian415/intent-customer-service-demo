<script setup lang="ts">
import { statusLabels } from '../types'

defineProps<{ status: string; label?: string }>()
</script>
<template>
  <span class="status-badge" :data-status="status">{{ label || statusLabels[status as keyof typeof statusLabels] || status }}</span>
</template>
<style scoped>
.status-badge { display: inline-flex; align-items: center; gap: 6px; flex: none; border: 1px solid #dedee2; border-radius: 7px; padding: 3px 8px; color: #424248; background: #fafafa; font-size: 12px; line-height: 1.6; white-space: nowrap; }
.status-badge::before { content: ''; width: 5px; height: 5px; flex: none; border-radius: 50%; background: #818189; }
.status-badge[data-status=processing]::before { background: #262628; }
.status-badge[data-status=resolved] { background: #fff8f1; border-color: #f2d8c0; color: #8e460b; }
.status-badge[data-status=resolved]::before { background: #e87517; }
.status-badge[data-status=closed] { color: #777780; background: #f5f5f6; }
</style>
