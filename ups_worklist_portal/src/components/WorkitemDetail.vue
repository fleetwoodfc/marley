<template>
  <div class="bg-white rounded-lg border border-gray-200 flex flex-col h-full max-h-[calc(100vh-12rem)] overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 flex-shrink-0">
      <h3 class="text-sm font-semibold text-gray-800">Workitem Detail</h3>
      <button
        class="text-gray-400 hover:text-gray-600 transition-colors"
        @click="$emit('close')"
      >
        <FeatherIcon name="x" class="w-4 h-4" />
      </button>
    </div>

    <!-- Content -->
    <div class="overflow-y-auto flex-1 p-4 space-y-4">
      <!-- State + priority -->
      <div class="flex items-center gap-2 flex-wrap">
        <span
          class="px-2.5 py-1 rounded-full text-xs font-medium"
          :class="stateBadgeClass(item.ups_state)"
        >{{ item.ups_state }}</span>
        <span
          class="px-2.5 py-1 rounded-full text-xs font-medium"
          :class="priorityClass(item.priority)"
        >{{ item.priority || 'ROUTINE' }}</span>
        <span
          v-if="item.cancel_requested_at"
          class="px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700"
        >Cancel Requested</span>
      </div>

      <!-- UID -->
      <div>
        <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Workitem UID</label>
        <p class="font-mono text-xs text-gray-700 mt-0.5 break-all">{{ item.name }}</p>
      </div>

      <!-- Patient -->
      <div>
        <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Patient</label>
        <p class="text-sm font-medium text-gray-800 mt-0.5">{{ item.patient_name || '—' }}</p>
      </div>

      <!-- Modality + AE -->
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Modality</label>
          <p class="text-sm text-gray-700 mt-0.5">{{ item.modality || '—' }}</p>
        </div>
        <div>
          <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">AE Title</label>
          <p class="text-sm font-mono text-gray-700 mt-0.5">{{ item.ae_title || '—' }}</p>
        </div>
      </div>

      <!-- Claimed by -->
      <div v-if="item.claimed_by">
        <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Claimed By</label>
        <p class="text-sm text-gray-700 mt-0.5">{{ item.claimed_by }}</p>
      </div>

      <!-- Timestamps -->
      <div class="grid grid-cols-2 gap-3 text-xs text-gray-500">
        <div>
          <span class="font-medium">Created:</span>
          <br />{{ formatDate(item.creation) }}
        </div>
        <div v-if="item.claimed_at">
          <span class="font-medium">Claimed:</span>
          <br />{{ formatDate(item.claimed_at) }}
        </div>
        <div v-if="item.completed_at">
          <span class="font-medium">Completed:</span>
          <br />{{ formatDate(item.completed_at) }}
        </div>
        <div v-if="item.cancel_requested_at">
          <span class="font-medium text-red-600">Cancel Req.:</span>
          <br />{{ formatDate(item.cancel_requested_at) }}
        </div>
      </div>

      <!-- Clinical indication / description -->
      <div v-if="item.procedure_description">
        <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Procedure</label>
        <p class="text-sm text-gray-700 mt-0.5">{{ item.procedure_description }}</p>
      </div>

      <!-- Linked SPS -->
      <div v-if="item.scheduled_procedure_step">
        <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Scheduled Procedure Step</label>
        <p class="font-mono text-xs text-blue-700 mt-0.5">{{ item.scheduled_procedure_step }}</p>
      </div>

      <!-- Performed Study UID -->
      <div v-if="item.performed_study_uid">
        <label class="text-xs text-gray-500 font-medium uppercase tracking-wider">Performed Study UID</label>
        <p class="font-mono text-xs text-gray-700 mt-0.5 break-all">{{ item.performed_study_uid }}</p>
      </div>
    </div>

    <!-- Action footer -->
    <div class="flex-shrink-0 border-t border-gray-200 px-4 py-3 flex flex-wrap gap-2">
      <!-- Claim -->
      <Button
        v-if="item.ups_state === 'SCHEDULED' && isTechnologist"
        size="sm"
        variant="solid"
        theme="blue"
        @click="$emit('claim', item.name)"
      >Claim</Button>

      <!-- Assign (supervisor) -->
      <Button
        v-if="isSupervisor && item.ups_state === 'SCHEDULED'"
        size="sm"
        variant="outline"
        @click="$emit('assign', item.name)"
      >Assign</Button>

      <!-- Complete -->
      <Button
        v-if="item.ups_state === 'IN PROGRESS' && (item.claimed_by === currentUser || isSupervisor)"
        size="sm"
        variant="solid"
        theme="green"
        @click="$emit('complete', item.name)"
      >Complete</Button>

      <!-- Request cancel (UC5) -->
      <Button
        v-if="['SCHEDULED', 'IN PROGRESS'].includes(item.ups_state) && isSupervisor"
        size="sm"
        variant="outline"
        theme="orange"
        @click="$emit('request-cancel', item.name)"
      >Request Cancel</Button>

      <!-- Performer self-cancel (UC6) -->
      <Button
        v-if="item.ups_state === 'IN PROGRESS' && item.claimed_by === currentUser"
        size="sm"
        variant="outline"
        theme="red"
        @click="$emit('performer-cancel', item.name)"
      >Cancel (Failure)</Button>

      <!-- Addendum (UC3) -->
      <Button
        v-if="item.ups_state === 'COMPLETED' && (isTechnologist || isSupervisor)"
        size="sm"
        variant="outline"
        theme="blue"
        @click="$emit('addendum', item.name)"
      >Create Addendum</Button>

      <!-- Audit log -->
      <Button
        size="sm"
        variant="ghost"
        @click="$emit('history', item.name)"
        title="View audit event history"
      >
        <FeatherIcon name="list" class="w-3 h-3 mr-1" />Log
      </Button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  item:          { type: Object,  required: true },
  aeMappings:    { type: Array,   default: () => [] },
  isSupervisor:  { type: Boolean, default: false },
  isTechnologist: { type: Boolean, default: false },
  currentUser:   { type: String,  default: '' },
})

defineEmits(['close', 'claim', 'assign', 'complete', 'cancel', 'request-cancel', 'performer-cancel', 'addendum', 'reschedule', 'history'])

function stateBadgeClass(state) {
  const map = {
    'SCHEDULED':   'bg-blue-100 text-blue-800',
    'IN PROGRESS': 'bg-orange-100 text-orange-800',
    'COMPLETED':   'bg-green-100 text-green-800',
    'CANCELED':    'bg-gray-100 text-gray-600',
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
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>
