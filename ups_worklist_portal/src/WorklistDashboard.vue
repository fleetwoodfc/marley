<template>
  <!-- Loading -->
  <div v-if="booting" class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="text-center">
      <Spinner class="mx-auto" />
      <p class="text-sm text-gray-500 mt-3">Loading dashboard…</p>
    </div>
  </div>

  <!-- Unauthenticated -->
  <div
    v-else-if="!authenticated"
    class="min-h-screen flex items-center justify-center bg-gray-50"
  >
    <div class="bg-white rounded-lg shadow p-8 w-full max-w-sm text-center">
      <div class="text-2xl font-bold text-gray-800 mb-1">UPS Worklist</div>
      <p class="text-sm text-gray-500 mb-6">Sign in to access the worklist dashboard.</p>
      <Button variant="solid" theme="blue" class="w-full" @click="redirectLogin">
        Sign In
      </Button>
    </div>
  </div>

  <!-- Main Dashboard -->
  <div v-else class="min-h-screen bg-gray-50 flex flex-col">
    <!-- ── Top bar ──────────────────────────────────────────────── -->
    <header class="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between sticky top-0 z-10">
      <div class="flex items-center gap-2">
        <!-- Icon -->
        <div class="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-blue-600 text-white flex-shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="9" y1="21" x2="9" y2="9" />
          </svg>
        </div>
        <span class="text-sm font-semibold text-gray-900">UPS Worklist Dashboard</span>
        <!-- Realtime indicator -->
        <span
          class="inline-block w-2 h-2 rounded-full ml-1"
          :class="connected ? 'bg-green-400' : 'bg-gray-300'"
          :title="connected ? 'Real-time connected' : 'Real-time disconnected'"
        />
      </div>
      <div class="flex items-center gap-3">
        <span class="text-xs text-gray-500 hidden sm:inline">{{ currentUser }}</span>
        <Badge
          v-if="primaryRole"
          size="sm"
          variant="subtle"
          :theme="primaryRole === 'UPS Supervisor' ? 'green' : 'blue'"
        >{{ primaryRole }}</Badge>
        <Button variant="ghost" size="sm" @click="reload">
          <FeatherIcon name="refresh-cw" class="w-3 h-3" />
        </Button>
      </div>
    </header>

    <!-- ── Summary bar ─────────────────────────────────────────── -->
    <SummaryBar :summary="summary" class="px-4 pt-3" />

    <!-- ── IHE tab navigation ──────────────────────────────────── -->
    <nav class="px-4 mt-3 border-b border-gray-200 bg-white">
      <ul class="flex gap-1 overflow-x-auto no-scrollbar">
        <li v-for="tab in TABS" :key="tab.id">
          <button
            class="relative px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors"
            :class="
              activeTab === tab.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            "
            :title="tab.title"
            @click="switchTab(tab.id)"
          >
            {{ tab.label }}
            <span
              v-if="tabCounts[tab.id] !== undefined"
              class="ml-1 text-xs px-1.5 py-0.5 rounded-full font-mono"
              :class="activeTab === tab.id ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'"
            >{{ tabCounts[tab.id] }}</span>
          </button>
        </li>
      </ul>
    </nav>

    <!-- ── Tab description ─────────────────────────────────────── -->
    <div v-if="activeTabDef" class="mx-4 mt-2">
      <Alert
        type="info"
        :title="activeTabDef.label"
      >{{ activeTabDef.title }}</Alert>
    </div>

    <!-- ── "All" filter bar ────────────────────────────────────── -->
    <FilterBar
      v-if="activeTab === 'all'"
      :ae-mappings="aeMappings"
      :is-supervisor-or-engineer="isSupervisorOrEngineer"
      v-model:status="filterStatus"
      v-model:ae-title="filterAet"
      v-model:modality="filterModality"
      v-model:patient="filterPatient"
      v-model:from-datetime="filterFrom"
      class="mx-4 mt-2"
      @apply="loadWorklist"
      @reconcile="showReconciliation = true"
    />

    <!-- ── Split: table + detail ───────────────────────────────── -->
    <div class="flex flex-1 gap-4 px-4 py-3 min-h-0">
      <!-- Worklist table -->
      <div :class="selectedItem ? 'w-full lg:w-3/5 xl:w-2/3' : 'w-full'" class="transition-all">
        <WorklistTable
          :items="worklist"
          :total="total"
          :loading="loading"
          :active-tab="activeTab"
          :selected-uid="selectedItem?.name"
          :is-technologist="isTechnologist"
          :is-supervisor="isSupervisor"
          :is-supervisor-or-engineer="isSupervisorOrEngineer"
          :current-user="currentUser"
          @select="selectItem"
          @claim="openClaim"
          @assign="openAssign"
          @complete="openComplete"
          @cancel="openCancel"
          @request-cancel="openRequestCancel"
          @performer-cancel="openPerformerCancel"
          @addendum="openAddendum"
          @reschedule="doReschedule"
          @history="openHistory"
        />
      </div>

      <!-- Detail side panel -->
      <transition name="slide">
        <div
          v-if="selectedItem"
          class="hidden lg:block lg:w-2/5 xl:w-1/3 flex-shrink-0"
        >
          <WorkitemDetail
            :item="selectedItem"
            :ae-mappings="aeMappings"
            :is-supervisor="isSupervisor"
            :is-technologist="isTechnologist"
            :current-user="currentUser"
            @close="selectedItem = null"
            @claim="openClaim"
            @assign="openAssign"
            @complete="openComplete"
            @cancel="openCancel"
            @request-cancel="openRequestCancel"
            @performer-cancel="openPerformerCancel"
            @addendum="openAddendum"
            @reschedule="doReschedule"
            @history="openHistory"
          />
        </div>
      </transition>
    </div>

    <!-- ── Reconciliation panel ────────────────────────────────── -->
    <div v-if="showReconciliation" class="px-4 pb-4">
      <ReconciliationPanel @close="showReconciliation = false" />
    </div>

    <!-- ══════════════════ Action Dialogs ═══════════════════════ -->

    <!-- Claim -->
    <Dialog v-model="claimDialogOpen" :options="{ title: 'Claim Workitem' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Select the performing AE for this workitem.
        </p>
        <div class="mb-2">
          <label class="block text-xs font-medium text-gray-700 mb-1">Performing AE Title</label>
          <select v-model="claimAet" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
            <option value="">— self / no AET —</option>
            <option v-for="ae in aeMappings" :key="ae.ae_title" :value="ae.ae_title">
              {{ ae.display_name || ae.ae_title }} ({{ ae.ae_title }})
            </option>
          </select>
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="blue" :loading="actionLoading" @click="doClaim">Claim</Button>
        <Button variant="ghost" @click="claimDialogOpen = false">Cancel</Button>
      </template>
    </Dialog>

    <!-- Assign (Supervisor) -->
    <Dialog v-model="assignDialogOpen" :options="{ title: 'Assign Workitem' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Assign workitem <code class="text-xs">{{ actionUid }}</code> to a specific Task Performer (UC2 / UC4).
        </p>
        <div class="mb-2">
          <label class="block text-xs font-medium text-gray-700 mb-1">Performer Station (AE Title) <span class="text-red-500">*</span></label>
          <select v-model="assignAet" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
            <option value="">Select station…</option>
            <option v-for="ae in assignFilteredMappings" :key="ae.ae_title" :value="ae.ae_title">
              {{ ae.display_name || ae.ae_title }} ({{ ae.ae_title }})
            </option>
          </select>
          <p class="text-xs text-gray-400 mt-1 italic">{{ assignClassHint }}</p>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Reason (optional)</label>
          <input v-model="assignReason" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                 placeholder="e.g. Radiologist on call">
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="blue" :loading="actionLoading" :disabled="!assignAet" @click="doAssign">
          Assign
        </Button>
        <Button variant="ghost" @click="assignDialogOpen = false">Cancel</Button>
      </template>
    </Dialog>

    <!-- Complete -->
    <Dialog v-model="completeDialogOpen" :options="{ title: 'Complete Workitem' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Mark workitem as COMPLETED. Optionally link the resulting study UID.
        </p>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Performed Study UID (optional)</label>
          <input v-model="studyUid" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm font-mono"
                 placeholder="2.25.xxxxx">
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="green" :loading="actionLoading" @click="doComplete">Complete</Button>
        <Button variant="ghost" @click="completeDialogOpen = false">Cancel</Button>
      </template>
    </Dialog>

    <!-- Cancel (Supervisor hard-cancel) -->
    <Dialog v-model="cancelDialogOpen" :options="{ title: 'Cancel Workitem' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Supervisor cancellation of workitem <code class="text-xs">{{ actionUid }}</code>.
        </p>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Reason</label>
          <input v-model="cancelReason" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                 placeholder="Reason for cancellation">
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="red" :loading="actionLoading" @click="doCancel">Cancel Workitem</Button>
        <Button variant="ghost" @click="cancelDialogOpen = false">Dismiss</Button>
      </template>
    </Dialog>

    <!-- Request Cancel (UC5 advisory) -->
    <Dialog v-model="requestCancelDialogOpen" :options="{ title: 'Request Cancellation (UC5)' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Send a cancel-request advisory to the Task Performer. The performer
          may honour or override the request.
        </p>
        <div class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">Reason</label>
            <input v-model="cancelReason" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                   placeholder="Reason for cancel request">
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">
              Contact Display Name
              <span class="text-gray-400 font-normal">(0074,100C) — optional</span>
            </label>
            <input v-model="cancelContactName" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                   placeholder="e.g. Dr. Jane Smith">
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">
              Contact URI
              <span class="text-gray-400 font-normal">(0074,100A) — optional</span>
            </label>
            <input v-model="cancelContactUri" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                   placeholder="e.g. sip:jsmith@hospital.org or mailto:jsmith@hospital.org">
          </div>
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="orange" :loading="actionLoading" @click="doRequestCancel">Send Cancel Request</Button>
        <Button variant="ghost" @click="requestCancelDialogOpen = false">Dismiss</Button>
      </template>
    </Dialog>

    <!-- Performer Cancel (UC6 self-cancel) -->
    <Dialog v-model="performerCancelDialogOpen" :options="{ title: 'Performer Cancel (UC6)' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Cancel this workitem due to a local failure. The workitem will
          transition to CANCELED and must be rescheduled by a supervisor.
        </p>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Reason</label>
          <input v-model="cancelReason" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                 placeholder="Describe the local failure">
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="red" :loading="actionLoading" @click="doPerformerCancel">Cancel (Failure)</Button>
        <Button variant="ghost" @click="performerCancelDialogOpen = false">Dismiss</Button>
      </template>
    </Dialog>

    <!-- Addendum (UC3) -->
    <Dialog v-model="addendumDialogOpen" :options="{ title: 'Create Addendum Workitem (UC3)' }">
      <template #body-content>
        <p class="text-sm text-gray-600 mb-3">
          Create a follow-up read workitem linked to the completed original.
        </p>
        <div class="mb-2">
          <label class="block text-xs font-medium text-gray-700 mb-1">Reason</label>
          <input v-model="addendumReason" type="text" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                 placeholder="e.g. Additional findings require review">
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Priority</label>
          <select v-model="addendumPriority" class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
            <option>LOW</option>
            <option>MEDIUM</option>
            <option>HIGH</option>
            <option>STAT</option>
          </select>
        </div>
      </template>
      <template #actions>
        <Button variant="solid" theme="blue" :loading="actionLoading" @click="doAddendum">Create Addendum</Button>
        <Button variant="ghost" @click="addendumDialogOpen = false">Cancel</Button>
      </template>
    </Dialog>

    <!-- Event History dialog -->
    <Dialog
      v-model="historyDialogOpen"
      :options="{ title: 'Event History', size: 'xl' }"
    >
      <template #body-content>
        <EventHistory :ups-uid="historyUid" />
      </template>
      <template #actions>
        <Button variant="ghost" @click="historyDialogOpen = false">Close</Button>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, inject } from 'vue'
import { frappeRequest } from 'frappe-ui'
import SummaryBar from './components/SummaryBar.vue'
import WorklistTable from './components/WorklistTable.vue'
import WorkitemDetail from './components/WorkitemDetail.vue'
import FilterBar from './components/FilterBar.vue'
import EventHistory from './components/EventHistory.vue'
import ReconciliationPanel from './components/ReconciliationPanel.vue'

const API = 'ups_worklist_portal.api.ups_actions'

// ── IHE RRR-WF §40.4.2 tab definitions ──────────────────────────────────────
const TABS = [
  {
    id:    'open',
    label: 'Open Worklist',
    title: 'UC1 — SCHEDULED workitems available for any qualified Task Performer to claim (community pool)',
  },
  {
    id:    'assigned',
    label: 'Assigned',
    title: 'UC2 / UC4 — SCHEDULED workitems assigned to a specific Task Performer; supervisor may re-assign',
  },
  {
    id:    'in_progress',
    label: 'In Progress',
    title: 'UC5 / UC6 — All IN PROGRESS (claimed) workitems; perform completion, cancel-request, or failure self-cancel',
  },
  {
    id:    'cancel_requested',
    label: 'Cancel Requested',
    title: 'UC5 — IN PROGRESS workitems with a pending cancel request awaiting performer action',
  },
  {
    id:    'addendum',
    label: 'Addendum',
    title: 'UC3 — Recently COMPLETED workitems; create an addendum workitem for a follow-up read',
  },
  {
    id:    'all',
    label: 'All Workitems',
    title: 'Unified filterable view across all states',
  },
]

// ── Socket ───────────────────────────────────────────────────────────────────
const socket = inject('$socket')

// ── State ────────────────────────────────────────────────────────────────────
const booting     = ref(true)
const authenticated = ref(false)
const currentUser = ref('')
const userRoles   = ref([])

const summary    = reactive({})
const aeMappings = ref([])
const worklist   = ref([])
const total      = ref(0)
const loading    = ref(false)
const tabCounts  = reactive({})

const activeTab    = ref('open')
const selectedItem = ref(null)
const connected    = ref(false)
const showReconciliation = ref(false)

// Filters (All tab)
const filterStatus   = ref(['SCHEDULED', 'IN PROGRESS'])
const filterAet      = ref('')
const filterModality = ref('')
const filterPatient  = ref('')
const filterFrom     = ref('')

// Dialog state
const actionUid    = ref(null)
const actionLoading = ref(false)

const claimDialogOpen          = ref(false)
const claimAet                 = ref('')
const assignDialogOpen         = ref(false)
const assignAet                = ref('')
const assignReason             = ref('')
const assignClassCode          = ref('')   // station_class_code from workitem being assigned
const assignClassHint          = ref('')   // user-visible filter hint (FR-010)
const completeDialogOpen       = ref(false)
const studyUid                 = ref('')
const cancelDialogOpen         = ref(false)
const requestCancelDialogOpen  = ref(false)
const performerCancelDialogOpen = ref(false)
const cancelReason             = ref('')
const cancelContactName        = ref('')
const cancelContactUri         = ref('')
const addendumDialogOpen       = ref(false)
const addendumReason           = ref('')
const addendumPriority         = ref('MEDIUM')
const historyDialogOpen        = ref(false)
const historyUid               = ref(null)

// ── Computed ─────────────────────────────────────────────────────────────────
const isTechnologist      = computed(() => userRoles.value.includes('UPS Technologist'))
const isSupervisor        = computed(() => userRoles.value.includes('UPS Supervisor'))
const isSupervisorOrEngineer = computed(() =>
  userRoles.value.some((r) => ['UPS Supervisor', 'UPS Integration Engineer'].includes(r))
)
const primaryRole = computed(() => {
  if (isSupervisor.value) return 'UPS Supervisor'
  if (isTechnologist.value) return 'UPS Technologist'
  if (userRoles.value.includes('UPS Integration Engineer')) return 'UPS Integration Engineer'
  return null
})
const activeTabDef = computed(() => TABS.find((t) => t.id === activeTab.value))

// FR-008/FR-009: filter AE Mappings by the workitem's station class code;
// falls back to all active mappings when no class code or no matches.
const assignFilteredMappings = computed(() => {
  const all = aeMappings.value.filter((m) => m.active !== 0)
  if (!assignClassCode.value) return all
  const matched = all.filter((m) => m.station_class_code === assignClassCode.value)
  return matched.length ? matched : all
})

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await checkAuth()
  if (authenticated.value) {
    await Promise.all([loadAeMappings(), loadSummary()])
    await loadWorklist()
    bindRealtime()
  }
  booting.value = false
})

onUnmounted(() => {
  if (socket) socket.off('ups_state_change')
})

// ── Auth ──────────────────────────────────────────────────────────────────────
async function checkAuth() {
  // Use user injected into boot by ups_worklist.py — avoids a network round-trip
  // and works regardless of which Frappe methods are whitelisted.
  const user = window.frappe_user
  if (user && user !== 'Guest') {
    authenticated.value = true
    currentUser.value = user
    userRoles.value = window.user_roles || []
  } else {
    authenticated.value = false
  }
}

function redirectLogin() {
  window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`
}

// ── Data loaders ──────────────────────────────────────────────────────────────
async function loadAeMappings() {
  try {
    const r = await frappeRequest({
      url: '/api/method/' + API + '.get_ae_mappings',
    })
    aeMappings.value = r || []
  } catch (e) {
    console.error('get_ae_mappings failed', e)
  }
}

async function loadSummary() {
  try {
    const r = await frappeRequest({
      url: '/api/method/' + API + '.get_dashboard_summary',
    })
    if (r) Object.assign(summary, r)
  } catch (e) {
    console.error('get_dashboard_summary failed', e)
  }
}

async function loadWorklist() {
  loading.value = true
  worklist.value = []
  try {
    let r
    if (activeTab.value === 'all') {
      r = await frappeRequest({
        url: '/api/method/' + API + '.get_worklist',
        params: {
          status: JSON.stringify(filterStatus.value),
          ae_title: filterAet.value,
          modality: filterModality.value,
          patient_name: filterPatient.value,
          from_datetime: filterFrom.value,
          limit: 50,
          offset: 0,
        },
      })
    } else {
      r = await frappeRequest({
        url: '/api/method/' + API + '.get_worklist_by_type',
        params: { worklist_type: activeTab.value, limit: 50, offset: 0 },
      })
    }
    if (r) {
      worklist.value = r.items || []
      total.value = r.total || 0
      tabCounts[activeTab.value] = r.total || 0
    }
  } catch (e) {
    console.error('load_worklist failed', e)
  } finally {
    loading.value = false
  }
}

// ── Realtime ──────────────────────────────────────────────────────────────────
function bindRealtime() {
  if (!socket) return
  connected.value = socket.connected

  socket.on('connect',    () => { connected.value = true })
  socket.on('disconnect', () => { connected.value = false })

  socket.on('ups_state_change', (data) => {
    // Refresh the row in-place if present, otherwise reload
    const idx = worklist.value.findIndex((i) => i.name === data.ups_uid)
    if (idx >= 0) {
      worklist.value[idx] = { ...worklist.value[idx], ...data }
      if (selectedItem.value?.name === data.ups_uid) {
        selectedItem.value = { ...selectedItem.value, ...data }
      }
    } else {
      loadWorklist()
    }
    loadSummary()
  })
}

// ── Navigation ────────────────────────────────────────────────────────────────
function switchTab(id) {
  activeTab.value = id
  selectedItem.value = null
  loadWorklist()
}

function reload() {
  loadSummary()
  loadWorklist()
}

function selectItem(item) {
  selectedItem.value = selectedItem.value?.name === item.name ? null : item
}

// ── Dialog openers ────────────────────────────────────────────────────────────
function openClaim(uid) {
  actionUid.value = uid
  claimAet.value = ''
  claimDialogOpen.value = true
}

function openAssign(uid) {
  actionUid.value = uid
  assignAet.value = ''
  assignReason.value = ''
  // FR-009/FR-010: extract class code from the already-loaded worklist row
  const item      = (worklist.value || []).find((w) => w.name === uid)
  const classCode = item?.scheduled_station_class_code || ''
  assignClassCode.value = classCode
  if (classCode) {
    const matched = aeMappings.value.filter(
      (m) => m.active !== 0 && m.station_class_code === classCode
    )
    assignClassHint.value = matched.length
      ? `Filtered to class «${classCode}» (0040,4026). ${matched.length} station(s) available.`
      : `Class «${classCode}» matched no stations — showing all.`
  } else {
    assignClassHint.value = 'No class filter — showing all active stations.'
  }
  assignDialogOpen.value = true
}

function openComplete(uid) {
  actionUid.value = uid
  studyUid.value = ''
  completeDialogOpen.value = true
}

function openCancel(uid) {
  actionUid.value = uid
  cancelReason.value = ''
  cancelDialogOpen.value = true
}

function openRequestCancel(uid) {
  actionUid.value = uid
  cancelReason.value = ''
  cancelContactName.value = ''
  cancelContactUri.value = ''
  requestCancelDialogOpen.value = true
}

function openPerformerCancel(uid) {
  actionUid.value = uid
  cancelReason.value = ''
  performerCancelDialogOpen.value = true
}

function openAddendum(uid) {
  actionUid.value = uid
  addendumReason.value = ''
  addendumPriority.value = 'MEDIUM'
  addendumDialogOpen.value = true
}

function openHistory(uid) {
  historyUid.value = uid
  historyDialogOpen.value = true
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function callAction(method, params, onSuccess) {
  actionLoading.value = true
  try {
    const r = await frappeRequest({
      url: '/api/method/' + API + '.' + method,
      params,
    })
    if (r !== undefined) onSuccess?.(r)
    await Promise.all([loadSummary(), loadWorklist()])
  } catch (e) {
    console.error(method + ' failed', e)
    alert('Action failed: ' + (e?.message || e))
  } finally {
    actionLoading.value = false
  }
}

async function doClaim() {
  await callAction('claim_workitem', { ups_uid: actionUid.value, performing_aet: claimAet.value || null }, () => {
    claimDialogOpen.value = false
  })
}

async function doAssign() {
  if (!assignAet.value) return
  await callAction('assign_workitem', {
    ups_uid: actionUid.value,
    performer_aet: assignAet.value,
    reason: assignReason.value || null,
  }, () => { assignDialogOpen.value = false })
}

async function doComplete() {
  await callAction('complete_workitem', {
    ups_uid: actionUid.value,
    performed_study_uid: studyUid.value || null,
  }, () => { completeDialogOpen.value = false })
}

async function doCancel() {
  await callAction('cancel_workitem', {
    ups_uid: actionUid.value,
    reason: cancelReason.value || null,
  }, () => { cancelDialogOpen.value = false })
}

async function doRequestCancel() {
  await callAction('request_workitem_cancel', {
    ups_uid: actionUid.value,
    reason: cancelReason.value || null,
    contact_display_name: cancelContactName.value || null,
    contact_uri: cancelContactUri.value || null,
  }, () => { requestCancelDialogOpen.value = false })
}

async function doPerformerCancel() {
  await callAction('performer_cancel_workitem', {
    ups_uid: actionUid.value,
    reason: cancelReason.value || null,
  }, () => { performerCancelDialogOpen.value = false })
}

async function doAddendum() {
  await callAction('create_addendum_workitem', {
    original_uid: actionUid.value,
    reason: addendumReason.value || null,
    priority: addendumPriority.value,
  }, () => { addendumDialogOpen.value = false })
}

async function doReschedule(uid) {
  await callAction('reschedule_workitem', { ups_uid: uid })
}
</script>
