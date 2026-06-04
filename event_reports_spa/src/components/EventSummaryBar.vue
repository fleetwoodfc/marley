<template>
  <div class="flex flex-wrap gap-2 pb-2">
    <span
      v-for="item in displayItems"
      :key="item.key"
      class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium"
      :class="item.classes"
    >
      <span class="w-1.5 h-1.5 rounded-full" :class="item.dotClass" />
      {{ item.label }}: {{ summary[item.key] ?? '—' }}
    </span>
  </div>
</template>

<script setup>
defineProps({
  summary: {
    type: Object,
    default: () => ({}),
  },
})

const displayItems = [
  { key: 'TOTAL',          label: 'Total',          classes: 'bg-gray-200 text-gray-800',           dotClass: 'bg-gray-500' },
  { key: 'CREATE',         label: 'Create',         classes: 'bg-blue-100 text-blue-800',           dotClass: 'bg-blue-500' },
  { key: 'CLAIM',          label: 'Claim',          classes: 'bg-indigo-100 text-indigo-800',       dotClass: 'bg-indigo-500' },
  { key: 'UPDATE',         label: 'Update',         classes: 'bg-amber-100 text-amber-800',         dotClass: 'bg-amber-500' },
  { key: 'COMPLETE',       label: 'Complete',       classes: 'bg-green-100 text-green-800',         dotClass: 'bg-green-500' },
  { key: 'CANCEL',         label: 'Cancel',         classes: 'bg-red-100 text-red-700',             dotClass: 'bg-red-500' },
  { key: 'CANCEL_REQUEST', label: 'Cancel Req',     classes: 'bg-orange-100 text-orange-700',       dotClass: 'bg-orange-500' },
  { key: 'REASSIGN',       label: 'Reassign',       classes: 'bg-purple-100 text-purple-800',       dotClass: 'bg-purple-500' },
  { key: 'RECONCILE',      label: 'Reconcile',      classes: 'bg-gray-100 text-gray-700',           dotClass: 'bg-gray-400' },
  { key: 'HTTP_ERROR',     label: 'HTTP Errors',    classes: 'bg-rose-100 text-rose-700',           dotClass: 'bg-rose-500' },
]
</script>
