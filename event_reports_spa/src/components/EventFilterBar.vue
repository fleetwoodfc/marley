<template>
  <div class="bg-white rounded-lg border border-gray-200 p-4">
    <div class="flex flex-wrap gap-3 items-end">

      <!-- Event type multi-select -->
      <div class="flex-1 min-w-[260px]">
        <label class="block text-xs font-medium text-gray-700 mb-1">Event Type</label>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="et in EVENT_TYPES"
            :key="et"
            class="px-2 py-1 text-xs rounded border transition-colors"
            :class="eventTypes.includes(et)
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-gray-300 text-gray-600 hover:border-gray-400'"
            @click="toggleEventType(et)"
          >{{ et }}</button>
        </div>
      </div>

      <!-- From datetime -->
      <div class="w-48">
        <label class="block text-xs font-medium text-gray-700 mb-1">From</label>
        <input
          :value="fromDatetime"
          type="datetime-local"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @input="$emit('update:fromDatetime', $event.target.value)"
        />
      </div>

      <!-- To datetime -->
      <div class="w-48">
        <label class="block text-xs font-medium text-gray-700 mb-1">To</label>
        <input
          :value="toDatetime"
          type="datetime-local"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @input="$emit('update:toDatetime', $event.target.value)"
        />
      </div>

      <!-- UPS Instance -->
      <div class="w-40">
        <label class="block text-xs font-medium text-gray-700 mb-1">UPS Instance</label>
        <input
          :value="upsInstance"
          type="text"
          placeholder="UID or name…"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm font-mono"
          @input="$emit('update:upsInstance', $event.target.value)"
          @keydown.enter="$emit('apply')"
        />
      </div>

      <!-- Actor -->
      <div class="w-36">
        <label class="block text-xs font-medium text-gray-700 mb-1">Actor</label>
        <input
          :value="actor"
          type="text"
          placeholder="User name…"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @input="$emit('update:actor', $event.target.value)"
          @keydown.enter="$emit('apply')"
        />
      </div>

      <!-- Actor AET -->
      <div class="w-28">
        <label class="block text-xs font-medium text-gray-700 mb-1">Actor AET</label>
        <input
          :value="actorAet"
          type="text"
          placeholder="AET…"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm font-mono"
          @input="$emit('update:actorAet', $event.target.value)"
          @keydown.enter="$emit('apply')"
        />
      </div>

      <!-- Actions -->
      <div class="flex gap-2 flex-shrink-0">
        <Button variant="solid" theme="blue" size="sm" @click="$emit('apply')">
          Apply
        </Button>
        <Button variant="ghost" size="sm" @click="resetFilters">
          Reset
        </Button>
        <Button
          v-if="canExport"
          variant="outline"
          size="sm"
          :loading="exportLoading"
          @click="$emit('export')"
        >
          <FeatherIcon name="download" class="w-3 h-3 mr-1" />
          Export CSV
        </Button>
      </div>

    </div>
  </div>
</template>

<script setup>
const EVENT_TYPES = [
  'CREATE', 'CLAIM', 'UPDATE', 'COMPLETE',
  'CANCEL', 'CANCEL_REQUEST', 'REASSIGN', 'RECONCILE',
]

const props = defineProps({
  eventTypes:    { type: Array,  default: () => [] },
  fromDatetime:  { type: String, default: '' },
  toDatetime:    { type: String, default: '' },
  upsInstance:   { type: String, default: '' },
  actor:         { type: String, default: '' },
  actorAet:      { type: String, default: '' },
  canExport:     { type: Boolean, default: false },
  exportLoading: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:eventTypes',
  'update:fromDatetime',
  'update:toDatetime',
  'update:upsInstance',
  'update:actor',
  'update:actorAet',
  'apply',
  'export',
])

function toggleEventType(et) {
  const current = [...props.eventTypes]
  const idx = current.indexOf(et)
  if (idx >= 0) {
    current.splice(idx, 1)
  } else {
    current.push(et)
  }
  emit('update:eventTypes', current)
}

function resetFilters() {
  emit('update:eventTypes', [])
  emit('update:fromDatetime', '')
  emit('update:toDatetime', '')
  emit('update:upsInstance', '')
  emit('update:actor', '')
  emit('update:actorAet', '')
  emit('apply')
}
</script>
