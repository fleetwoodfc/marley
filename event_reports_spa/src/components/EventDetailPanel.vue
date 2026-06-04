<template>
  <div class="bg-white rounded-lg border border-gray-200 h-full overflow-y-auto flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 sticky top-0 bg-white z-10">
      <div class="flex items-center gap-2">
        <span
          class="px-2 py-0.5 rounded text-xs font-semibold"
          :class="eventTypeClass(event.event_type)"
        >{{ event.event_type }}</span>
        <span class="text-xs text-gray-500 font-mono">{{ event.name }}</span>
      </div>
      <button
        class="text-gray-400 hover:text-gray-600 transition-colors"
        @click="$emit('close')"
      >
        <FeatherIcon name="x" class="w-4 h-4" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-10">
      <LoadingIndicator class="mr-2 w-5 h-5" />
      <span class="text-sm text-gray-500">Loading details…</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="p-4">
      <Alert type="error" title="Failed to load event">{{ error }}</Alert>
    </div>

    <!-- Content -->
    <div v-else-if="detail" class="p-4 space-y-4 flex-1">

      <!-- Core fields -->
      <section>
        <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Event</h3>
        <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt class="text-xs text-gray-500">Timestamp</dt>
            <dd class="font-mono text-gray-800 text-xs">{{ formatDatetime(detail.event_timestamp) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-gray-500">HTTP Status</dt>
            <dd>
              <span
                v-if="detail.http_status"
                class="px-1.5 py-0.5 rounded text-xs font-mono font-medium"
                :class="detail.http_status >= 400 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'"
              >{{ detail.http_status }}</span>
              <span v-else class="text-gray-400 text-xs">—</span>
            </dd>
          </div>
          <div>
            <dt class="text-xs text-gray-500">Actor</dt>
            <dd class="text-gray-800 text-xs">{{ detail.actor || '—' }}</dd>
          </div>
          <div>
            <dt class="text-xs text-gray-500">Actor AET</dt>
            <dd class="font-mono text-gray-800 text-xs">{{ detail.actor_aet || '—' }}</dd>
          </div>
        </dl>
      </section>

      <!-- UPS instance -->
      <section>
        <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">UPS Instance</h3>
        <p class="font-mono text-xs text-gray-800 break-all">{{ detail.ups_instance || '—' }}</p>
      </section>

      <!-- State transition -->
      <section v-if="detail.old_state || detail.new_state">
        <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">State Transition</h3>
        <div class="flex items-center gap-2">
          <span
            v-if="detail.old_state"
            class="px-2 py-0.5 rounded text-xs font-medium"
            :class="stateClass(detail.old_state)"
          >{{ detail.old_state }}</span>
          <FeatherIcon v-if="detail.old_state && detail.new_state" name="arrow-right" class="w-4 h-4 text-gray-400" />
          <span
            v-if="detail.new_state"
            class="px-2 py-0.5 rounded text-xs font-medium"
            :class="stateClass(detail.new_state)"
          >{{ detail.new_state }}</span>
        </div>
      </section>

      <!-- Event Report Information (DICOM Sup96 Table UUU.2.4-1) -->
      <EventReportInfo :raw-request="detail.raw_request" :event-type="detail.event_type" />

      <!-- Transaction UID -->
      <section v-if="detail.transaction_uid">
        <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Transaction UID</h3>
        <p class="font-mono text-xs text-gray-800 break-all">{{ detail.transaction_uid }}</p>
      </section>

      <!-- Details text -->
      <section v-if="detail.details">
        <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Details</h3>
        <p class="text-xs text-gray-700 whitespace-pre-wrap">{{ detail.details }}</p>
      </section>

      <!-- Raw Audit Data (audit roles only — backend controls visibility) -->
      <section v-if="detail.raw_request || detail.raw_response">
        <button
          class="flex items-center gap-1 text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
          @click="rawExpanded = !rawExpanded"
        >
          <FeatherIcon :name="rawExpanded ? 'chevron-down' : 'chevron-right'" class="w-3 h-3" />
          Raw Audit Data
        </button>
        <div v-if="rawExpanded" class="space-y-2">
          <div v-if="detail.raw_request">
            <p class="text-xs font-medium text-gray-500 mb-1">Request</p>
            <pre class="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">{{ prettyJson(detail.raw_request) }}</pre>
          </div>
          <div v-if="detail.raw_response">
            <p class="text-xs font-medium text-gray-500 mb-1">Response</p>
            <pre class="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">{{ prettyJson(detail.raw_response) }}</pre>
          </div>
        </div>
      </section>

    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { frappeRequest } from 'frappe-ui'
import EventReportInfo from './EventReportInfo.vue'

const props = defineProps({
  event: { type: Object, required: true },
})

defineEmits(['close'])

const API = 'healthcare.ups_worklist_portal.api.event_reports'

const detail      = ref(null)
const loading     = ref(false)
const error       = ref(null)
const rawExpanded = ref(false)

watch(
  () => props.event?.name,
  (name) => { if (name) load(name) },
  { immediate: true },
)

async function load(name) {
  loading.value     = true
  error.value       = null
  rawExpanded.value = false
  try {
    detail.value = await frappeRequest({
      url: `/api/method/${API}.get_event`,
      params: { name },
    })
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

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

function prettyJson(str) {
  if (!str) return ''
  try {
    return JSON.stringify(JSON.parse(str), null, 2)
  } catch {
    return str
  }
}
</script>
