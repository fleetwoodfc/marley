<template>
  <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
    <!-- Loading skeleton -->
    <div v-if="loading" class="p-6 text-center text-sm text-gray-500">
      <Spinner class="mx-auto mb-2" />
      Loading worklist…
    </div>

    <!-- Empty state -->
    <div v-else-if="!items.length" class="p-8 text-center text-sm text-gray-400">
      <FeatherIcon name="inbox" class="w-8 h-8 mx-auto mb-2 text-gray-300" />
      No workitems found in this view.
    </div>

    <!-- Table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th v-if="activeTab !== 'open'" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">State</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Patient</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Step Label</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Station Class</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Station Name</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Priority</th>
            <th
              v-if="activeTab === 'in_progress' || activeTab === 'all'"
              class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
            >Claimed By</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
            <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-100">
          <tr
            v-for="item in items"
            :key="item.name"
            class="worklist-row transition-colors"
            :class="{
              'selected': item.name === selectedUid,
              'row-cancel-requested': !!item.cancel_requested_at,
            }"
            @click="$emit('select', item)"
          >
            <!-- State badge -->
            <td v-if="activeTab !== 'open'" class="px-3 py-2 whitespace-nowrap">
              <span
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                :class="stateBadgeClass(item.ups_state)"
              >{{ item.ups_state }}</span>
              <span
                v-if="item.cancel_requested_at"
                class="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700"
              >Cancel Req.</span>
            </td>

            <!-- Patient -->
            <td class="px-3 py-2">
              <div class="font-medium text-gray-800">{{ item.patient_name || '—' }}</div>
              <div class="text-xs text-gray-400">{{ item.patient_id || '—' }}</div>
            </td>

            <!-- Step Label -->
            <td class="px-3 py-2 text-xs text-gray-600">{{ item.procedure_description || item.protocol_name || '—' }}</td>

            <!-- Station Class -->
            <td class="px-3 py-2 font-mono text-xs text-gray-600">{{ item.scheduled_station_class_code || '—' }}</td>

            <!-- Station Name -->
            <td class="px-3 py-2 font-mono text-xs text-gray-600">{{ item.scheduled_station_name || '—' }}</td>

            <!-- Priority -->
            <td class="px-3 py-2">
              <span
                class="text-xs font-medium px-1.5 py-0.5 rounded"
                :class="priorityClass(item.priority)"
              >{{ item.priority || '—' }}</span>
            </td>

            <!-- Claimed By (in-progress / all) -->
            <td
              v-if="activeTab === 'in_progress' || activeTab === 'all'"
              class="px-3 py-2 text-xs text-gray-500"
            >{{ item.claimed_by || '—' }}</td>

            <!-- Created -->
            <td class="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">
              {{ formatDate(item.creation || item.order_datetime) }}
            </td>

            <!-- Actions -->
            <td class="px-3 py-2 text-right whitespace-nowrap" @click.stop>
              <div class="flex items-center justify-end gap-1">
                <!-- UC1/UC2: Claim -->
                <Button
                  v-if="canClaim(item)"
                  size="sm"
                  variant="solid"
                  theme="blue"
                  @click="$emit('claim', item.name)"
                >Claim</Button>

                <!-- UC2/UC4: Assign (Supervisor) -->
                <Button
                  v-if="isSupervisor && (activeTab === 'open' || activeTab === 'assigned') && item.ups_state === 'SCHEDULED'"
                  size="sm"
                  variant="outline"
                  @click="$emit('assign', item.name)"
                >Assign</Button>

                <!-- UC5/UC6: Complete -->
                <Button
                  v-if="canComplete(item)"
                  size="sm"
                  variant="solid"
                  theme="green"
                  @click="$emit('complete', item.name)"
                >Complete</Button>

                <!-- UC6: Performer self-cancel -->
                <Button
                  v-if="canPerformerCancel(item)"
                  size="sm"
                  variant="outline"
                  theme="red"
                  @click="$emit('performer-cancel', item.name)"
                >Cancel</Button>

                <!-- UC5: Request cancel advisory -->
                <Button
                  v-if="canRequestCancel(item)"
                  size="sm"
                  variant="outline"
                  theme="orange"
                  @click="$emit('request-cancel', item.name)"
                >Req. Cancel</Button>

                <!-- UC3: Addendum -->
                <Button
                  v-if="activeTab === 'addendum' && (isTechnologist || isSupervisor)"
                  size="sm"
                  variant="outline"
                  theme="blue"
                  @click="$emit('addendum', item.name)"
                >Addendum</Button>

                <!-- Supervisor: hard cancel (open/assigned/cancel_requested tabs) -->
                <Button
                  v-if="isSupervisor && (activeTab === 'open' || activeTab === 'assigned' || activeTab === 'cancel_requested')"
                  size="sm"
                  variant="ghost"
                  theme="red"
                  @click="$emit('cancel', item.name)"
                >Cancel</Button>

                <!-- Supervisor: reschedule orphaned -->
                <Button
                  v-if="isSupervisor && activeTab === 'in_progress'"
                  size="sm"
                  variant="ghost"
                  @click="$emit('reschedule', item.name)"
                >Reschedule</Button>

                <!-- Audit log (privileged) -->
                <Button
                  v-if="isSupervisorOrEngineer"
                  size="sm"
                  variant="ghost"
                  @click="$emit('history', item.name)"
                  title="Audit event log"
                >
                  <FeatherIcon name="list" class="w-3 h-3" />
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Footer -->
      <div class="px-3 py-2 bg-gray-50 border-t border-gray-200 text-xs text-gray-500">
        Showing {{ items.length }} of {{ total }} workitems
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  items:               { type: Array,   default: () => [] },
  total:               { type: Number,  default: 0 },
  loading:             { type: Boolean, default: false },
  activeTab:           { type: String,  default: 'open' },
  selectedUid:         { type: String,  default: null },
  isTechnologist:      { type: Boolean, default: false },
  isSupervisor:        { type: Boolean, default: false },
  isSupervisorOrEngineer: { type: Boolean, default: false },
  currentUser:         { type: String,  default: '' },
})

defineEmits([
  'select', 'claim', 'assign', 'complete', 'cancel',
  'request-cancel', 'performer-cancel', 'addendum', 'reschedule', 'history',
])

// ── Helpers ──────────────────────────────────────────────────────────────────
function stateBadgeClass(state) {
  const map = {
    'SCHEDULED':   'bg-blue-100 text-blue-800',
    'IN PROGRESS': 'bg-orange-100 text-orange-800',
    'COMPLETED':   'bg-green-100 text-green-800',
    'CANCELED':    'bg-gray-100 text-gray-600',
    'SYNC_ERROR':  'bg-red-100 text-red-700',
  }
  return map[state] || 'bg-gray-100 text-gray-600'
}

function priorityClass(priority) {
  const map = {
    STAT:    'bg-red-100 text-red-700',
    HIGH:    'bg-orange-100 text-orange-700',
    MEDIUM:  'bg-yellow-100 text-yellow-700',
    LOW:     'bg-gray-100 text-gray-500',
    ROUTINE: 'bg-gray-100 text-gray-500',
  }
  return map[priority] || 'bg-gray-100 text-gray-500'
}

function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── Action visibility ─────────────────────────────────────────────────────────
function canClaim(item) {
  return item.ups_state === 'SCHEDULED' && props.isTechnologist
}

function canComplete(item) {
  if (item.ups_state !== 'IN PROGRESS') return false
  return item.claimed_by === props.currentUser || props.isSupervisor
}

function canPerformerCancel(item) {
  if (item.ups_state !== 'IN PROGRESS') return false
  const tab = props.activeTab
  return (tab === 'in_progress' || tab === 'cancel_requested') &&
         (item.claimed_by === props.currentUser || props.isSupervisor)
}

function canRequestCancel(item) {
  if (!['SCHEDULED', 'IN PROGRESS'].includes(item.ups_state)) return false
  const tab = props.activeTab
  return (tab === 'in_progress' || tab === 'all') &&
         (props.isTechnologist || props.isSupervisor)
}
</script>
