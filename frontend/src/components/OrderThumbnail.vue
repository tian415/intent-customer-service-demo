<script setup lang="ts">
import { computed } from 'vue'
import type { Order } from '../types'
import ServiceIcon from './ServiceIcon.vue'
import keyboardPhoto from '../assets/support/keyboard.jpg'
import flaskPhoto from '../assets/support/flask.jpg'
import earbudsPhoto from '../assets/support/earbuds.jpg'

const props = defineProps<{ order: Order }>()
const demoPhotos: Record<string, { name: string; src: string }> = {
  DEMO20261103001: { name: '无线蓝牙耳机', src: earbudsPhoto },
  DEMO20261103002: { name: '保温杯 500ml', src: flaskPhoto },
  DEMO20261103003: { name: '机械键盘套件', src: keyboardPhoto },
}
const src = computed(() => {
  const photo = demoPhotos[props.order.order_no]
  return photo?.name === props.order.product_name ? photo.src : undefined
})
</script>
<template>
  <span class="order-thumbnail" aria-hidden="true">
    <img v-if="src" :src="src" alt="" />
    <ServiceIcon v-else name="box" />
  </span>
</template>
<style scoped>
.order-thumbnail { display: inline-grid; place-items: center; flex: none; width: 42px; height: 42px; border-radius: 10px; overflow: hidden; background: #eeeef0; color: #52525b; }
.order-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
</style>
