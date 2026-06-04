<template>
  <div class="bg-white rounded-lg border border-gray-200 p-4">
    <div class="flex flex-wrap gap-3 items-end">
      <!-- Status multi-select -->
      <div class="flex-1 min-w-[160px]">
        <label class="block text-xs font-medium text-gray-700 mb-1">Status</label>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="s in STATES"
            :key="s"
            class="px-2 py-1 text-xs rounded border transition-colors"
            :class="status.includes(s)
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-gray-300 text-gray-600 hover:border-gray-400'"
            @click="toggleStatus(s)"
          >{{ s }}</button>
        </div>
      </div>

      <!-- AE Title -->
      <div class="w-44">
        <label class="block text-xs font-medium text-gray-700 mb-1">AE Title</label>
        <select
          :value="aeTitle"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @change="$emit('update:ae-title', $event.target.value)"
        >
          <option value="">All AE Titles</option>
          <option v-for="ae in aeMappings" :key="ae.ae_title" :value="ae.ae_title">
            {{ ae.display_name || ae.ae_title }}
          </option>
        </select>
      </div>

      <!-- Modality -->
      <div class="w-28">
        <label class="block text-xs font-medium text-gray-700 mb-1">Modality</label>
        <input
          :value="modality"
          type="text"
          placeholder="CT, MR…"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @input="$emit('update:modality', $event.target.value)"
          @keydown.enter="$emit('apply')"
        />
      </div>

      <!-- Patient name -->
      <div class="w-40">
        <label class="block text-xs font-medium text-gray-700 mb-1">Patient</label>
        <input
          :value="patient"
          type="text"
          placeholder="Search name…"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @input="$emit('update:patient', $event.target.value)"
          @keydown.enter="$emit('apply')"
        />
      </div>

      <!-- From datetime -->
      <div class="w-44">
        <label class="block text-xs font-medium text-gray-700 mb-1">From</label>
        <input
          :value="fromDatetime"
          type="datetime-local"
          class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          @input="$emit('update:from-datetime', $event.target.value)"
        />
      </div>

      <!-- Buttons -->
      <div class="flex gap-2">
        <Button variant="solid" theme="blue" size="sm" @click="$emit('apply')">Apply</Button>
        <Button v-if="isSupervisorOrEngineer" variant="outline" size="sm" @click="$emit('reconcile')">
          Reconciliation…
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup>
const STATES = ['SCHEDULED', 'IN PROGRESS', 'COMPLETED', 'CANCELED']

const props = defineProps({
  aeMappings:           { type: Array,   default: () => [] },
  isSupervisorOrEngineer: { type: Boolean, default: false },
  status:               { type: Array,   default: () => ['SCHEDULED', 'IN PROGRESS'] },
  aeTitle:              { type: String,  default: '' },
  modality:             { type: String,  default: '' },
  patient:              { type: String,  default: '' },
  fromDatetime:         { type: String,  default: '' },
})

const emit = defineEmits([
  'update:status', 'update:ae-title', 'update:modality',
  'update:patient', 'update:from-datetime',
  'apply', 'reconcile',
])

function toggleStatus(s) {
  const current = [...props.status]
  const idx = current.indexOf(s)
  if (idx >= 0) {
    current.splice(idx, 1)
  } else {
    current.push(s)
  }
  emit('update:status', current)
}
</script>
