<template>
  <div class="flex flex-col gap-4">

    <!-- Active subscriptions table -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm font-semibold text-gray-700">Active Filtered Subscriptions</h3>
        <button
          class="text-gray-400 hover:text-gray-600 transition-colors"
          title="Refresh"
          @click="loadList"
        >
          <FeatherIcon name="refresh-cw" class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- Loading -->
      <div v-if="listLoading" class="flex items-center gap-2 py-4 text-sm text-gray-400">
        <LoadingIndicator class="w-4 h-4" />
        <span>Loading…</span>
      </div>

      <!-- Error -->
      <Alert v-else-if="listError" type="error" title="Error">{{ listError }}</Alert>

      <!-- Empty -->
      <div
        v-else-if="!subscriptions.length"
        class="text-sm text-gray-400 italic py-4 text-center border border-dashed border-gray-200 rounded"
      >
        No active filtered subscriptions.
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-xs border border-gray-200 rounded">
          <thead>
            <tr class="bg-gray-50 text-left text-gray-500">
              <th class="px-3 py-2 font-medium">DICOM Tag</th>
              <th class="px-3 py-2 font-medium">Description</th>
              <th class="px-3 py-2 font-medium">Matching Value</th>
              <th class="px-3 py-2 font-medium">Subscribed At</th>
              <th class="px-3 py-2 font-medium">By</th>
              <th class="px-3 py-2 font-medium">WS URL</th>
              <th class="px-3 py-2 font-medium">Event Reports</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="sub in subscriptions" :key="sub.name" class="hover:bg-gray-50">
              <td class="px-3 py-2 font-mono text-gray-800">{{ sub.matching_tag }}</td>
              <td class="px-3 py-2 text-gray-600">{{ sub.matching_tag_label || '—' }}</td>
              <td class="px-3 py-2 font-mono font-medium text-gray-900">{{ sub.matching_value }}</td>
              <td class="px-3 py-2 text-gray-500 whitespace-nowrap">{{ formatDatetime(sub.subscribed_at) }}</td>
              <td class="px-3 py-2 text-gray-500 truncate max-w-[10rem]">{{ sub.subscribed_by || '—' }}</td>
              <td class="px-3 py-2 font-mono text-gray-400 truncate max-w-[14rem]">
                <span v-if="sub.ws_url" :title="sub.ws_url">{{ sub.ws_url }}</span>
                <span v-else class="italic">—</span>
              </td>
              <td class="px-3 py-2">
                <a
                  :href="subscriptionDashboardUrl(sub)"
                  :title="`Open Event Reports filtered to ${sub.matching_value}`"
                  class="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 text-xs font-medium whitespace-nowrap"
                >
                  <FeatherIcon name="external-link" class="w-3 h-3" />
                  View events
                </a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- DICOM standard note -->
    <p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 leading-relaxed">
      <strong>Note:</strong> The DICOM UPS standard does not support removing individual filtered
      subscriptions. <strong>Remove All</strong> sends a single DELETE to dcm4chee-arc that removes
      every filtered subscription for this portal AE. Re-add any subscriptions you want to keep.
    </p>

    <!-- Actions row -->
    <div v-if="canManage" class="flex items-start gap-3 flex-wrap">

      <!-- Add subscription inline form -->
      <div class="flex-1 min-w-[280px] border border-gray-200 rounded p-3 space-y-2 bg-gray-50">
        <p class="text-xs font-semibold text-gray-700">Add Filtered Subscription</p>

        <!-- Tag selector -->
        <div>
          <label class="block text-xs text-gray-600 mb-1">DICOM Tag</label>
          <select
            v-model="form.tagPreset"
            class="w-full border border-gray-300 rounded px-2 py-1.5 text-xs bg-white"
            @change="onPresetChange"
          >
            <option value="">— select or enter custom —</option>
            <option v-for="p in TAG_PRESETS" :key="p.tag" :value="p.tag">
              {{ p.label }} ({{ p.tag }})
            </option>
            <option value="__custom__">Custom tag…</option>
          </select>
        </div>

        <!-- Custom tag input (shown when __custom__ selected) -->
        <div v-if="form.tagPreset === '__custom__'">
          <label class="block text-xs text-gray-600 mb-1">
            Tag (8 hex chars, e.g. <span class="font-mono">00741202</span>)
          </label>
          <input
            v-model="form.customTag"
            type="text"
            class="w-full border border-gray-300 rounded px-2 py-1.5 text-xs font-mono"
            placeholder="00741202"
            maxlength="17"
          />
        </div>

        <!-- Custom description (only shown for custom tag) -->
        <div v-if="form.tagPreset === '__custom__'">
          <label class="block text-xs text-gray-600 mb-1">Description (optional)</label>
          <input
            v-model="form.customLabel"
            type="text"
            class="w-full border border-gray-300 rounded px-2 py-1.5 text-xs"
            placeholder="e.g. Worklist Label"
          />
        </div>

        <!-- Matching value -->
        <div>
          <label class="block text-xs text-gray-600 mb-1">Matching Value</label>
          <input
            v-model="form.value"
            type="text"
            class="w-full border border-gray-300 rounded px-2 py-1.5 text-xs font-mono"
            placeholder="e.g. CT-POOL-A"
            @keydown.enter="doAdd"
          />
        </div>

        <!-- Add error -->
        <p v-if="addError" class="text-xs text-red-600">{{ addError }}</p>

        <Button
          variant="solid"
          theme="blue"
          size="sm"
          :loading="addLoading"
          :disabled="!canSubmitAdd"
          @click="doAdd"
        >
          Subscribe
        </Button>
      </div>

      <!-- Remove all -->
      <div class="flex flex-col gap-1">
        <template v-if="!confirmRemove">
          <Button
            variant="outline"
            size="sm"
            :disabled="!subscriptions.length"
            @click="confirmRemove = true"
          >
            <FeatherIcon name="trash-2" class="w-3 h-3 mr-1 text-red-500" />
            Remove All
          </Button>
        </template>
        <template v-else>
          <p class="text-xs text-red-600 font-medium">Remove all {{ subscriptions.length }} subscription(s)?</p>
          <div class="flex gap-2">
            <Button variant="solid" theme="red" size="sm" :loading="removeLoading" @click="doRemoveAll">
              Confirm
            </Button>
            <Button variant="ghost" size="sm" @click="confirmRemove = false">Cancel</Button>
          </div>
        </template>
        <p v-if="removeError" class="text-xs text-red-600">{{ removeError }}</p>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { frappeRequest } from 'frappe-ui'

const props = defineProps({
  canManage: { type: Boolean, default: false },
})

const API = 'healthcare.ups_worklist_portal.api.event_reports'

// ── Common DICOM tag presets ──────────────────────────────────────────────
const TAG_PRESETS = [
  { tag: '00741202',         label: 'Worklist Label' },
  { tag: '00404025.00080100', label: 'Station Name Code Value' },
  { tag: '00404026.00080100', label: 'Station Class Code Value' },
  { tag: '0040A040',         label: 'Value Type' },
]

// ── State ─────────────────────────────────────────────────────────────────
const subscriptions = ref([])
const listLoading   = ref(false)
const listError     = ref(null)

// Add form
const form = ref({ tagPreset: '', customTag: '', customLabel: '', value: '' })
const addLoading    = ref(false)
const addError      = ref(null)

// Remove all
const confirmRemove = ref(false)
const removeLoading = ref(false)
const removeError   = ref(null)

// ── Computed ──────────────────────────────────────────────────────────────
const resolvedTag = computed(() => {
  if (form.value.tagPreset === '__custom__') return form.value.customTag.trim()
  return form.value.tagPreset
})

const resolvedLabel = computed(() => {
  if (form.value.tagPreset === '__custom__') return form.value.customLabel.trim()
  return TAG_PRESETS.find((p) => p.tag === form.value.tagPreset)?.label || ''
})

const canSubmitAdd = computed(() => {
  return resolvedTag.value.length >= 8 && form.value.value.trim().length > 0
})

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(loadList)

// ── Methods ───────────────────────────────────────────────────────────────
async function loadList() {
  listLoading.value = true
  listError.value   = null
  try {
    const r = await frappeRequest({
      url: `/api/method/${API}.list_filtered_subscriptions`,
    })
    subscriptions.value = Array.isArray(r) ? r : (r?.message ?? [])
  } catch (e) {
    listError.value = e?.message || String(e)
  } finally {
    listLoading.value = false
  }
}

function onPresetChange() {
  form.value.customTag   = ''
  form.value.customLabel = ''
  form.value.value       = ''
  addError.value = null
}

async function doAdd() {
  if (!canSubmitAdd.value) return
  addLoading.value = true
  addError.value   = null
  try {
    await frappeRequest({
      url: `/api/method/${API}.create_filtered_subscription`,
      params: {
        matching_tag:       resolvedTag.value,
        matching_tag_label: resolvedLabel.value,
        matching_value:     form.value.value.trim(),
      },
    })
    // Reset form
    form.value = { tagPreset: '', customTag: '', customLabel: '', value: '' }
    await loadList()
  } catch (e) {
    addError.value = e?.message || String(e)
  } finally {
    addLoading.value = false
  }
}

async function doRemoveAll() {
  removeLoading.value = true
  removeError.value   = null
  try {
    await frappeRequest({
      url: `/api/method/${API}.delete_all_filtered_subscriptions`,
    })
    confirmRemove.value = false
    await loadList()
  } catch (e) {
    removeError.value = e?.message || String(e)
  } finally {
    removeLoading.value = false
  }
}

function formatDatetime(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString(undefined, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// Tags whose matching_value maps to actor_aet in the event log
const _AET_TAGS = new Set([
  '00741202',          // Worklist Label
  '00404025.00080100', // Station Name Code Value
  '00404026.00080100', // Station Class Code Value
])

function subscriptionDashboardUrl(sub) {
  const base = window.location.pathname  // /event_reports
  const params = new URLSearchParams()
  if (_AET_TAGS.has(sub.matching_tag)) {
    params.set('actor_aet', sub.matching_value)
  }
  const qs = params.toString()
  return qs ? `${base}?${qs}` : base
}
</script>
