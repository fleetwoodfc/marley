<template>
  <div class="space-y-3">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-gray-500">
      <LoadingIndicator class="w-4 h-4" />
      Loading event history…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-sm text-red-600">{{ error }}</div>

    <!-- Empty -->
    <div v-else-if="!events.length" class="text-sm text-gray-400 text-center py-4">
      No events recorded for this workitem.
    </div>

    <!-- Events timeline -->
    <div v-else class="relative pl-4">
      <div
        v-for="(ev, idx) in events"
        :key="idx"
        class="relative pb-4 last:pb-0"
      >
        <!-- Timeline line -->
        <div
          v-if="idx < events.length - 1"
          class="absolute left-0 top-4 bottom-0 w-px bg-gray-200"
          style="transform: translateX(-0.5px);"
        />
        <!-- Dot -->
        <div class="absolute left-0 top-1.5 w-2 h-2 rounded-full bg-white border-2 border-blue-400"
             style="transform: translateX(-4px);" />

        <div class="ml-3">
          <div class="flex items-baseline gap-2 flex-wrap">
            <span class="text-xs font-semibold text-gray-800">{{ ev.event_type || ev.type }}</span>
            <span class="text-xs text-gray-400">{{ formatDate(ev.creation || ev.event_datetime) }}</span>
            <span v-if="ev.performed_by" class="text-xs text-gray-500">by {{ ev.performed_by }}</span>
          </div>
          <p v-if="ev.description || ev.reason" class="text-xs text-gray-600 mt-0.5">
            {{ ev.description || ev.reason }}
          </p>
          <p v-if="ev.new_state" class="text-xs mt-0.5">
            <span class="text-gray-500">→ state:</span>
            <span
              class="ml-1 px-1.5 py-0.5 rounded text-xs font-medium"
              :class="stateBadgeClass(ev.new_state)"
            >{{ ev.new_state }}</span>
          </p>
          <!-- DICOM N-EVENT-REPORT structured attributes (Sup96 Table UUU.2.4-1) -->
          <EventReportInfo
            v-if="ev.raw_request"
            :raw-request="ev.raw_request"
            :event-type="ev.event_type || ev.type"
            class="mt-2"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { frappeRequest, LoadingIndicator } from 'frappe-ui'
import EventReportInfo from './EventReportInfo.vue'

const props = defineProps({
  upsUid: { type: String, required: true },
})

const API = 'ups_worklist_portal.api.ups_actions'
const events  = ref([])
const loading = ref(false)
const error   = ref(null)

onMounted(load)
watch(() => props.upsUid, load)

async function load() {
  if (!props.upsUid) return
  loading.value = true
  error.value   = null
  try {
    const r = await frappeRequest({
      url: '/api/method/' + API + '.get_event_history',
      params: { ups_uid: props.upsUid },
    })
    events.value = Array.isArray(r) ? r : []
  } catch (e) {
    error.value = 'Failed to load event history: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
}

function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function stateBadgeClass(state) {
  const map = {
    'SCHEDULED':   'bg-blue-100 text-blue-800',
    'IN PROGRESS': 'bg-orange-100 text-orange-800',
    'COMPLETED':   'bg-green-100 text-green-800',
    'CANCELED':    'bg-gray-100 text-gray-600',
  }
  return map[state] || 'bg-gray-100 text-gray-600'
}
</script>
