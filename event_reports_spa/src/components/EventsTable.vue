<template>
  <div class="flex flex-col overflow-hidden rounded-lg border border-gray-200 bg-white">
    <!-- Loading state -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <LoadingIndicator class="mr-2 w-5 h-5" />
      <span class="text-sm text-gray-500">Loading events…</span>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!items.length"
      class="flex flex-col items-center justify-center py-12 text-center"
    >
      <FeatherIcon name="inbox" class="w-8 h-8 text-gray-300 mb-2" />
      <p class="text-sm text-gray-400">No events match the current filters.</p>
    </div>

    <!-- Table -->
    <template v-else>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 bg-gray-50 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <th class="px-3 py-2">Timestamp</th>
              <th class="px-3 py-2">Type</th>
              <th class="px-3 py-2">Actor</th>
              <th class="px-3 py-2">State Transition</th>
              <th class="px-3 py-2">Details</th>
              <th class="px-3 py-2 text-center">HTTP</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="ev in items"
              :key="ev.name"
              class="event-row border-b border-gray-100 last:border-0 transition-colors"
              :class="{ active: selectedName === ev.name }"
              @click="$emit('select', ev)"
            >
              <!-- Timestamp -->
              <td class="px-3 py-2 whitespace-nowrap font-mono text-xs text-gray-600">
                {{ formatDatetime(ev.event_timestamp) }}
              </td>

              <!-- Event type badge -->
              <td class="px-3 py-2 whitespace-nowrap">
                <span
                  class="px-1.5 py-0.5 rounded text-xs font-semibold"
                  :class="eventTypeClass(ev.event_type)"
                >{{ ev.event_type }}</span>
              </td>

              <!-- Actor -->
              <td class="px-3 py-2 text-gray-700 text-xs truncate max-w-[120px]">
                <span>{{ ev.actor || '—' }}</span>
                <span v-if="ev.actor_aet" class="ml-1 text-gray-400 font-mono">({{ ev.actor_aet }})</span>
              </td>

              <!-- State Transition -->
              <td class="px-3 py-2 whitespace-nowrap text-xs">
                <span v-if="ev.old_state || ev.new_state" class="flex items-center gap-1">
                  <span
                    v-if="ev.old_state"
                    class="px-1.5 py-0.5 rounded text-xs font-medium"
                    :class="stateClass(ev.old_state)"
                  >{{ ev.old_state }}</span>
                  <FeatherIcon v-if="ev.old_state && ev.new_state" name="arrow-right" class="w-3 h-3 text-gray-400 flex-shrink-0" />
                  <span
                    v-if="ev.new_state"
                    class="px-1.5 py-0.5 rounded text-xs font-medium"
                    :class="stateClass(ev.new_state)"
                  >{{ ev.new_state }}</span>
                </span>
                <span v-else class="text-gray-300">—</span>
              </td>

              <!-- Details -->
              <td class="px-3 py-2 text-xs text-gray-600 truncate max-w-[200px]"
                  :title="ev.details">
                {{ ev.details || '—' }}
              </td>

              <!-- HTTP status -->
              <td class="px-3 py-2 text-center">
                <span
                  v-if="ev.http_status"
                  class="px-1.5 py-0.5 rounded text-xs font-mono font-medium"
                  :class="ev.http_status >= 400 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'"
                >{{ ev.http_status }}</span>
                <span v-else class="text-gray-300 text-xs">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div
        v-if="total > items.length || offset > 0"
        class="flex items-center justify-between px-4 py-2 border-t border-gray-200 bg-gray-50"
      >
        <span class="text-xs text-gray-500">
          Showing {{ offset + 1 }}–{{ Math.min(offset + items.length, total) }} of {{ total }}
        </span>
        <div class="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            :disabled="offset === 0"
            @click="$emit('prev-page')"
          >
            <FeatherIcon name="chevron-left" class="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            :disabled="offset + items.length >= total"
            @click="$emit('next-page')"
          >
            <FeatherIcon name="chevron-right" class="w-4 h-4" />
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
defineProps({
  items:        { type: Array,   default: () => [] },
  total:        { type: Number,  default: 0 },
  offset:       { type: Number,  default: 0 },
  loading:      { type: Boolean, default: false },
  selectedName: { type: String,  default: null },
})

defineEmits(['select', 'prev-page', 'next-page'])

const EVENT_TYPE_CLASSES = {
  CREATE:         'bg-blue-100 text-blue-800',
  CLAIM:          'bg-indigo-100 text-indigo-800',
  UPDATE:         'bg-amber-100 text-amber-800',
  COMPLETE:       'bg-green-100 text-green-800',
  CANCEL:         'bg-red-100 text-red-700',
  CANCEL_REQUEST: 'bg-orange-100 text-orange-700',
  REASSIGN:       'bg-purple-100 text-purple-800',
  RECONCILE:      'bg-gray-100 text-gray-700',
}

const STATE_CLASSES = {
  'SCHEDULED':   'bg-blue-100 text-blue-800',
  'IN PROGRESS': 'bg-orange-100 text-orange-800',
  'COMPLETED':   'bg-green-100 text-green-800',
  'CANCELED':    'bg-gray-100 text-gray-600',
}

function eventTypeClass(type) {
  return EVENT_TYPE_CLASSES[type] || 'bg-gray-100 text-gray-600'
}

function stateClass(state) {
  return STATE_CLASSES[state] || 'bg-gray-100 text-gray-600'
}

function formatDatetime(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>
