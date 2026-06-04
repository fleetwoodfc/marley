<template>
  <div class="flex flex-wrap gap-2 pb-2">
    <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
      <span class="w-1.5 h-1.5 rounded-full bg-blue-500" />
      Scheduled: {{ summary.SCHEDULED ?? '—' }}
    </span>
    <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
      <span class="w-1.5 h-1.5 rounded-full bg-orange-500" />
      In Progress: {{ summary.IN_PROGRESS ?? '—' }}
    </span>
    <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
      <span class="w-1.5 h-1.5 rounded-full bg-green-500" />
      Completed: {{ summary.COMPLETED ?? '—' }}
    </span>
    <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
      <span class="w-1.5 h-1.5 rounded-full bg-gray-400" />
      Canceled: {{ summary.CANCELED ?? '—' }}
    </span>
    <span
      v-if="summary.SYNC_ERROR > 0"
      class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-red-500" />
      Sync Errors: {{ summary.SYNC_ERROR }}
    </span>
    <span
      v-if="summary.ORPHANED > 0"
      class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-yellow-500" />
      Orphaned: {{ summary.ORPHANED }}
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
</script>
