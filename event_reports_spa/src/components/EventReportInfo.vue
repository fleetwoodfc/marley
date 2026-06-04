<template>
  <section v-if="info" class="mt-4">
    <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-indigo-500" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      Event Report Information
      <span v-if="info.eventTypeId" class="ml-1 px-1.5 py-0.5 rounded text-xs font-normal bg-indigo-50 text-indigo-600 border border-indigo-100">
        {{ EVENT_TYPE_ID_LABELS[info.eventTypeId] || `Type ${info.eventTypeId}` }}
      </span>
    </h3>

    <dl class="space-y-1.5">

      <!-- Procedure Step State (0074,1000) -->
      <div v-if="info.procedureStepState" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1000)</code> Procedure Step State
        </dt>
        <dd>
          <span class="px-1.5 py-0.5 rounded font-medium" :class="stateClass(info.procedureStepState)">
            {{ info.procedureStepState }}
          </span>
        </dd>
      </div>

      <!-- Input Readiness State (0040,4041) -->
      <div v-if="info.inputReadinessState" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0040,4041)</code> Input Readiness State
        </dt>
        <dd class="text-gray-800">{{ info.inputReadinessState }}</dd>
      </div>

      <!-- Requesting AE (0074,1236) – Cancel Requested -->
      <div v-if="info.requestingAe" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1236)</code> Requesting AE
        </dt>
        <dd class="font-mono text-gray-800">{{ info.requestingAe }}</dd>
      </div>

      <!-- Reason For Cancellation (0074,1238) -->
      <div v-if="info.reasonForCancellation" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1238)</code> Reason For Cancellation
        </dt>
        <dd class="text-gray-800">{{ info.reasonForCancellation }}</dd>
      </div>

      <!-- Discontinuation Reason Code Sequence (0074,100E) -->
      <div v-if="info.discontinuationReasonCodes?.length" class="text-xs">
        <dt class="text-gray-500 flex items-center gap-1 mb-1">
          <code class="text-gray-400">(0074,100E)</code> Discontinuation Reason
        </dt>
        <dd>
          <ul class="space-y-0.5 pl-2">
            <li
              v-for="(code, idx) in info.discontinuationReasonCodes"
              :key="idx"
              class="text-gray-800 text-xs"
            >
              {{ code.formatted || code.meaning || code.value }}
            </li>
          </ul>
        </dd>
      </div>

      <!-- Contact URI (0074,100A) -->
      <div v-if="info.contactUri" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,100A)</code> Contact URI
        </dt>
        <dd class="font-mono text-gray-800 break-all">{{ info.contactUri }}</dd>
      </div>

      <!-- Contact Display Name (0074,100C) -->
      <div v-if="info.contactDisplayName" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,100C)</code> Contact Display Name
        </dt>
        <dd class="text-gray-800">{{ info.contactDisplayName }}</dd>
      </div>

      <!-- Progress (0074,1004) -->
      <div v-if="info.stepProgress != null" class="text-xs">
        <dt class="text-gray-500 flex items-center gap-1 mb-1">
          <code class="text-gray-400">(0074,1004)</code> Procedure Step Progress
        </dt>
        <dd>
          <div class="flex items-center gap-2">
            <div class="flex-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">
              <div
                class="bg-blue-500 h-1.5 rounded-full"
                :style="{ width: `${Math.min(100, Math.max(0, info.stepProgress))}%` }"
              />
            </div>
            <span class="text-gray-800 font-mono w-9 text-right">{{ info.stepProgress }}%</span>
          </div>
        </dd>
      </div>

      <!-- Progress Description (0074,1006) -->
      <div v-if="info.stepProgressDesc" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1006)</code> Progress Description
        </dt>
        <dd class="text-gray-800">{{ info.stepProgressDesc }}</dd>
      </div>

      <!-- Communications URI Sequence (0074,1008) -->
      <div v-if="info.commsContacts?.length" class="text-xs">
        <dt class="text-gray-500 flex items-center gap-1 mb-1">
          <code class="text-gray-400">(0074,1008)</code> Communications URI
        </dt>
        <dd>
          <ul class="space-y-1 pl-2">
            <li v-for="(c, idx) in info.commsContacts" :key="idx" class="text-gray-800">
              <span v-if="c.name" class="font-medium">{{ c.name }}: </span>
              <span class="font-mono break-all">{{ c.uri }}</span>
            </li>
          </ul>
        </dd>
      </div>

      <!-- SCP Status (0074,1242) -->
      <div v-if="info.scpStatus" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1242)</code> SCP Status
        </dt>
        <dd class="text-gray-800">{{ info.scpStatus }}</dd>
      </div>

      <!-- Subscription List Status (0074,1244) -->
      <div v-if="info.subscriptionListStatus" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1244)</code> Subscription List Status
        </dt>
        <dd class="text-gray-800">{{ info.subscriptionListStatus }}</dd>
      </div>

      <!-- UPS List Status (0074,1246) -->
      <div v-if="info.upsListStatus" class="grid grid-cols-2 gap-x-3 text-xs">
        <dt class="text-gray-500 flex items-center gap-1">
          <code class="text-gray-400">(0074,1246)</code> UPS List Status
        </dt>
        <dd class="text-gray-800">{{ info.upsListStatus }}</dd>
      </div>

    </dl>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { extractEventReportInfo, EVENT_TYPE_ID_LABELS } from '../dicomTags.js'

const props = defineProps({
  /** The raw_request field content (DICOM+JSON string or null) */
  rawRequest: { type: String, default: null },
  /** The application-level event_type string (e.g. 'CLAIM', 'CANCEL_REQUEST') */
  eventType: { type: String, default: '' },
})

const info = computed(() => extractEventReportInfo(props.rawRequest, props.eventType))

const STATE_CLASSES = {
  'SCHEDULED':   'bg-blue-100 text-blue-800',
  'IN PROGRESS': 'bg-orange-100 text-orange-800',
  'COMPLETED':   'bg-green-100 text-green-800',
  'CANCELED':    'bg-gray-100 text-gray-600',
}

function stateClass(state) {
  return STATE_CLASSES[state] || 'bg-gray-100 text-gray-600'
}
</script>
