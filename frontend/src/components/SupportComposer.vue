<script setup lang="ts">
import ServiceIcon from './ServiceIcon.vue'

const draft = defineModel<string>({ required: true })
defineProps<{ busy: boolean; disabled?: boolean; placeholder?: string }>()
const emit = defineEmits<{ send: []; handoff: [] }>()
function onEnter(event: KeyboardEvent) {
  if (event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  emit('send')
}
</script>
<template>
  <form class="support-compose" @submit.prevent="emit('send')">
    <label class="sr-only" for="support-draft">咨询内容</label>
    <textarea id="support-draft" v-model="draft" rows="2" maxlength="10000" :disabled="disabled" :placeholder="placeholder ?? '输入你的售后问题…'" @keydown.enter="onEnter" />
    <div class="compose-actions">
      <button type="button" class="handoff-link" :disabled="busy || disabled" @click="emit('handoff')"><ServiceIcon name="headset" />人工</button>
      <button type="submit" class="send-action wx-send" aria-label="发送" :disabled="busy || disabled || !draft.trim()"><ServiceIcon name="send" /></button>
    </div>
  </form>
</template>
