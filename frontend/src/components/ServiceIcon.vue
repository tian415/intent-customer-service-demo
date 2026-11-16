<script setup lang="ts">
const paths = {
  inbox: 'M4 4h16v16H4z M4 13h5l1 3h4l1-3h5',
  settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  search: 'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z m-2 5 6 6',
  back: 'M20 12H5 M11 6l-6 6 6 6',
  station: 'm2 8 10-5 10 5-10 5z M2 12l10 5 10-5 M2 16l10 5 10-5',
  chat: 'M20 12a8 8 0 0 1-8 8H4l1.3-4.2A8 8 0 1 1 20 12Z M8.5 10h7 M8.5 13.5h4.5',
  orders: 'M6 3h12v18l-3-2-3 2-3-2-3 2z M9 8h6 M9 12h6',
  user: 'M15.5 8a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Z M5 20v-1a7 7 0 0 1 14 0v1',
  logout: 'M10 4H5v16h5 M9 12h11 M16 8l4 4-4 4',
  policy: 'M3 5c3.5-.8 6.3-.2 9 1.6C14.7 4.8 17.5 4.2 21 5v13c-3.5-.8-6.3-.2-9 1.6-2.7-1.8-5.5-2.4-9-1.6Z M12 7v12',
  refund: 'M9 5 4 10l5 5 M4 10h10.5a5 5 0 0 1 0 10H12',
  clock: 'M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9Z M12 7v5l3.5 2',
  truck: 'M3 6h11v10H9 M3 16h2 M14 9h3.5l3.5 4v3h-2 M14 16h1 M9 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z M19 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
  arrow: 'M4 12h15 M13 6l6 6-6 6',
  diagonal: 'M6 18 18 6 M6 6h12v12',
  send: 'M12 19V5 M6 11l6-6 6 6',
  headset: 'M4 15v-3a8 8 0 0 1 16 0v4a4 4 0 0 1-4 4h-3 M4 11H3v5h4v-5H4Z M20 11h1v5h-4v-5h3Z',
  box: 'm3 7 9-4.5L21 7v10l-9 4.5L3 17z M3 7l9 4.5L21 7 M12 11.5v10 M7.5 4.8l9 4.5',
  refresh: 'M4.5 10a8 8 0 1 1 .5 6 M4 4v6h6',
  check: 'm5 12 4 4 10-10',
} as const

defineProps<{ name: keyof typeof paths }>()
</script>
<template>
  <svg class="service-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path :d="paths[name]" />
  </svg>
</template>
<style scoped>
.service-icon { width: 1.25em; height: 1.25em; flex: none; }
</style>
