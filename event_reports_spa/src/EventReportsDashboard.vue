<template>
  <!-- Loading -->
  <div v-if="booting" class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="text-center">
      <LoadingIndicator class="mx-auto w-8 h-8" />
      <p class="text-sm text-gray-500 mt-3">Loading…</p>
    </div>
  </div>

  <!-- Unauthenticated -->
  <div
    v-else-if="!authenticated"
    class="min-h-screen flex items-center justify-center bg-gray-50"
  >
    <div class="bg-white rounded-lg shadow p-8 w-full max-w-sm text-center">
      <div class="text-2xl font-bold text-gray-800 mb-1">UPS Event Reports</div>
      <p class="text-sm text-gray-500 mb-6">Sign in to access the event audit dashboard.</p>
      <Button variant="solid" theme="blue" class="w-full" @click="redirectLogin">
        Sign In
      </Button>
    </div>
  </div>

  <!-- Main dashboard -->
  <div v-else class="min-h-screen bg-gray-50 flex flex-col">

    <!-- ── Header ──────────────────────────────────── -->
    <header class="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between sticky top-0 z-10">
      <div class="flex items-center gap-2">
        <div class="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-600 text-white flex-shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
        </div>
        <span class="text-sm font-semibold text-gray-900">UPS Event Reports</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-xs text-gray-500 hidden sm:inline">{{ currentUser }}</span>
        <!-- Subscriptions panel — read-only for Supervisor, full management for Integration Engineer (FR-012) -->
        <Button
          v-if="isIntegrationEngineer || isSupervisor"
          variant="ghost"
          size="sm"
          title="Manage DICOM Filtered Subscriptions"
          @click="subscriptionsOpen = true"
        >
          <FeatherIcon name="radio" class="w-3 h-3" />
        </Button>
        <Button variant="ghost" size="sm" :loading="loading" @click="reload">
          <FeatherIcon name="refresh-cw" class="w-3 h-3" />
        </Button>
      </div>
    </header>

    <!-- ── Summary bar ───────────────────────────── -->
    <EventSummaryBar :summary="summary" class="px-4 pt-3" />

    <!-- ── Filter bar ────────────────────────────── -->
    <div class="px-4 mt-1">
      <EventFilterBar
        v-model:event-types="filterEventTypes"
        v-model:from-datetime="filterFrom"
        v-model:to-datetime="filterTo"
        v-model:ups-instance="filterUpsInstance"
        v-model:actor="filterActor"
        v-model:actor-aet="filterActorAet"
        :can-export="canExport"
        :export-loading="exportLoading"
        @apply="onApply"
        @export="onExport"
      />
    </div>

    <!-- ── Pre-filter banner (set by URL query params from a subscription link) ── -->
    <div
      v-if="preFilterLabel"
      class="mx-4 mt-2 px-3 py-2 rounded bg-indigo-50 border border-indigo-200 flex items-center justify-between gap-2"
    >
      <div class="flex items-center gap-2 text-xs text-indigo-800">
        <FeatherIcon name="filter" class="w-3 h-3 flex-shrink-0" />
        <span>Pre-filtered from subscription: <strong>{{ preFilterLabel }}</strong></span>
      </div>
      <button
        class="text-indigo-400 hover:text-indigo-700 transition-colors flex-shrink-0"
        title="Clear pre-filter"
        @click="clearPreFilter"
      >
        <FeatherIcon name="x" class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- ── Error banner ──────────────────────────── -->
    <div v-if="errorMsg" class="mx-4 mt-2">
      <Alert type="error" title="Error">{{ errorMsg }}</Alert>
    </div>

    <!-- ── Split: table + detail ─────────────────── -->
    <div class="flex flex-1 gap-4 px-4 py-3 min-h-0">
      <!-- Events table -->
      <div :class="selectedEvent ? 'w-full lg:w-3/5 xl:w-2/3' : 'w-full'" class="transition-all">
        <EventsTable
          :items="events"
          :total="total"
          :offset="offset"
          :loading="loading"
          :selected-name="selectedEvent?.name"
          @select="onSelectEvent"
          @prev-page="prevPage"
          @next-page="nextPage"
        />
      </div>

      <!-- Detail panel -->
      <transition name="slide">
        <div
          v-if="selectedEvent"
          class="hidden lg:block lg:w-2/5 xl:w-1/3 flex-shrink-0"
        >
          <EventDetailPanel
            :event="selectedEvent"
            @close="selectedEvent = null"
          />
        </div>
      </transition>
    </div>

    <!-- ── Export success toast ──────────────────── -->
    <div
      v-if="exportToast"
      class="fixed bottom-4 right-4 bg-white border border-gray-200 rounded-lg shadow-lg px-4 py-3 flex items-center gap-2 z-50"
    >
      <FeatherIcon name="check-circle" class="w-4 h-4 text-green-500" />
      <span class="text-sm text-gray-700">{{ exportToast }}</span>
    </div>
    <!-- ── DICOM Filtered Subscriptions dialog ────────────────────────────── -->
    <Dialog
      v-model="subscriptionsOpen"
      :options="{ title: 'DICOM Filtered Subscriptions', size: '3xl' }"
    >
      <template #body-content>
        <SubscriptionsPanel :can-manage="isIntegrationEngineer" />
      </template>
      <template #actions>
        <Button variant="ghost" @click="subscriptionsOpen = false">Close</Button>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { frappeRequest } from 'frappe-ui'

import EventSummaryBar    from './components/EventSummaryBar.vue'
import EventFilterBar     from './components/EventFilterBar.vue'
import EventsTable        from './components/EventsTable.vue'
import EventDetailPanel   from './components/EventDetailPanel.vue'
import SubscriptionsPanel from './components/SubscriptionsPanel.vue'

const API = 'healthcare.ups_worklist_portal.api.event_reports'
const PAGE_SIZE = 50

// ── Auth / boot ──────────────────────────────────────────────────────────────
const booting       = ref(true)
const authenticated = ref(false)
const currentUser   = ref('')
const userRoles     = ref([])

const AUDIT_ROLES = ['UPS Supervisor', 'UPS Integration Engineer']
const ALL_PORTAL_ROLES = ['UPS Technologist', 'UPS Supervisor', 'UPS Integration Engineer']

const canExport = computed(() =>
  AUDIT_ROLES.some((r) => userRoles.value.includes(r)),
)

const isIntegrationEngineer = computed(() =>
  userRoles.value.includes('UPS Integration Engineer'),
)

const isSupervisor = computed(() =>
  userRoles.value.includes('UPS Supervisor'),
)

// ── Subscriptions dialog ─────────────────────────────────────────────────────
const subscriptionsOpen = ref(false)

// ── Pre-filter (from URL query params) ──────────────────────────────────────
const preFilterLabel = ref('')

function _applyUrlParams() {
  const p = new URLSearchParams(window.location.search)
  const parts = []
  if (p.get('actor_aet')) {
    filterActorAet.value = p.get('actor_aet')
    parts.push(`Actor AET = ${p.get('actor_aet')}`)
  }
  if (p.get('actor')) {
    filterActor.value = p.get('actor')
    parts.push(`Actor = ${p.get('actor')}`)
  }
  if (p.get('ups_instance')) {
    filterUpsInstance.value = p.get('ups_instance')
    parts.push(`UPS Instance = ${p.get('ups_instance')}`)
  }
  if (p.get('event_types')) {
    try {
      const parsed = JSON.parse(p.get('event_types'))
      if (Array.isArray(parsed) && parsed.length) {
        filterEventTypes.value = parsed
        parts.push(`Types = ${parsed.join(', ')}`)
      }
    } catch {
      // ignore malformed
    }
  }
  if (p.get('from')) { filterFrom.value = p.get('from') }
  if (p.get('to'))   { filterTo.value   = p.get('to') }
  preFilterLabel.value = parts.join(' · ')
}

function clearPreFilter() {
  preFilterLabel.value   = ''
  filterActorAet.value   = ''
  filterActor.value      = ''
  filterUpsInstance.value = ''
  filterEventTypes.value = []
  filterFrom.value       = ''
  filterTo.value         = ''
  // Remove query string without page reload
  window.history.replaceState({}, '', window.location.pathname)
  onApply()
}

// ── Data state ───────────────────────────────────────────────────────────────
const events        = ref([])
const total         = ref(0)
const offset        = ref(0)
const loading       = ref(false)
const errorMsg      = ref(null)
const summary       = ref({})
const selectedEvent = ref(null)

// ── Filter state ─────────────────────────────────────────────────────────────
const filterEventTypes  = ref([])
const filterFrom        = ref('')
const filterTo          = ref('')
const filterUpsInstance = ref('')
const filterActor       = ref('')
const filterActorAet    = ref('')

// ── Export ───────────────────────────────────────────────────────────────────
const exportLoading = ref(false)
const exportToast   = ref('')

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  const user  = window.frappe_user || ''
  const roles = window.user_roles  || []
  currentUser.value = user
  userRoles.value   = roles

  if (!user || user === 'Guest') {
    booting.value = false
    return
  }

  if (!ALL_PORTAL_ROLES.some((r) => roles.includes(r))) {
    redirectLogin()
    return
  }

  authenticated.value = true
  booting.value = false
  _applyUrlParams()
  await reload()
})

// ── Load data ────────────────────────────────────────────────────────────────
async function reload() {
  offset.value = 0
  await Promise.all([loadEvents(), loadSummary()])
}

async function loadEvents() {
  loading.value  = true
  errorMsg.value = null
  try {
    const r = await frappeRequest({
      url: `/api/method/${API}.get_event_list`,
      params: buildParams(),
    })
    events.value = r?.items ?? []
    total.value  = r?.total  ?? 0
  } catch (e) {
    errorMsg.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  try {
    summary.value = await frappeRequest({
      url: `/api/method/${API}.get_event_summary`,
      params: {
        from_datetime: filterFrom.value || undefined,
        to_datetime:   filterTo.value   || undefined,
      },
    })
  } catch {
    // non-fatal — summary is decorative
  }
}

// ── Filter helpers ───────────────────────────────────────────────────────────
function buildParams() {
  return {
    event_types:  filterEventTypes.value.length ? JSON.stringify(filterEventTypes.value) : undefined,
    from_datetime: filterFrom.value        || undefined,
    to_datetime:   filterTo.value          || undefined,
    ups_instance:  filterUpsInstance.value || undefined,
    actor:         filterActor.value       || undefined,
    actor_aet:     filterActorAet.value    || undefined,
    limit:  PAGE_SIZE,
    offset: offset.value,
  }
}

function onApply() {
  offset.value = 0
  selectedEvent.value = null
  loadEvents()
  loadSummary()
}

// ── Pagination ───────────────────────────────────────────────────────────────
async function prevPage() {
  if (offset.value === 0) return
  offset.value = Math.max(0, offset.value - PAGE_SIZE)
  await loadEvents()
}

async function nextPage() {
  if (offset.value + PAGE_SIZE >= total.value) return
  offset.value += PAGE_SIZE
  await loadEvents()
}

// ── Event selection ──────────────────────────────────────────────────────────
function onSelectEvent(ev) {
  selectedEvent.value = selectedEvent.value?.name === ev.name ? null : ev
}

// ── CSV export ───────────────────────────────────────────────────────────────
async function onExport() {
  exportLoading.value = true
  try {
    const r = await frappeRequest({
      url: `/api/method/${API}.export_events_csv`,
      params: {
        event_types:   filterEventTypes.value.length ? JSON.stringify(filterEventTypes.value) : undefined,
        from_datetime: filterFrom.value        || undefined,
        to_datetime:   filterTo.value          || undefined,
        ups_instance:  filterUpsInstance.value || undefined,
        actor:         filterActor.value       || undefined,
        actor_aet:     filterActorAet.value    || undefined,
      },
    })

    if (r?.csv) {
      const blob = new Blob([r.csv], { type: 'text/csv;charset=utf-8;' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `ups_events_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      showToast(`Exported ${r.count ?? ''} events`)
    }
  } catch (e) {
    errorMsg.value = 'Export failed: ' + (e?.message || e)
  } finally {
    exportLoading.value = false
  }
}

function showToast(msg) {
  exportToast.value = msg
  setTimeout(() => { exportToast.value = '' }, 3000)
}

// ── Auth helpers ─────────────────────────────────────────────────────────────
function redirectLogin() {
  window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`
}
</script>
