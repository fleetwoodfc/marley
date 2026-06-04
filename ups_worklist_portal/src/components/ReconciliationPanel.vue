<template>
  <div class="bg-white rounded-lg border border-gray-200 p-4">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-semibold text-gray-800">Reconciliation — PACS ↔ DB Diff</h3>
      <Button variant="ghost" size="sm" @click="$emit('close')">
        <FeatherIcon name="x" class="w-4 h-4" />
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-gray-500 py-4">
      <Spinner /> Loading reconciliation diff…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-sm text-red-600 py-4">{{ error }}</div>

    <!-- Empty -->
    <div v-else-if="!items.length" class="py-6 text-center text-sm text-gray-400">
      <FeatherIcon name="check-circle" class="w-8 h-8 mx-auto mb-2 text-green-400" />
      No discrepancies detected between PACS and DB.
    </div>

    <!-- Diff table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <thead>
          <tr class="bg-gray-50 border-b border-gray-200">
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Workitem UID</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">PACS State</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">DB State</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Diff Type</th>
            <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-for="item in items" :key="item.ups_uid" class="hover:bg-gray-50">
            <td class="px-3 py-2 font-mono text-xs text-gray-700">{{ item.ups_uid?.slice(0, 24) }}…</td>
            <td class="px-3 py-2">
              <span class="px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                {{ item.pacs_state || '—' }}
              </span>
            </td>
            <td class="px-3 py-2">
              <span class="px-1.5 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                {{ item.db_state || '—' }}
              </span>
            </td>
            <td class="px-3 py-2 text-xs text-gray-600">{{ item.diff_type }}</td>
            <td class="px-3 py-2 text-right">
              <div class="flex items-center justify-end gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  theme="blue"
                  :loading="processingUid === item.ups_uid"
                  @click="accept(item.ups_uid, 'sync_from_pacs')"
                >
                  Sync from PACS
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  :loading="processingUid === item.ups_uid"
                  @click="accept(item.ups_uid, 'ignore')"
                >
                  Ignore
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Reload -->
    <div class="mt-4 flex justify-end">
      <Button variant="ghost" size="sm" @click="load">
        <FeatherIcon name="refresh-cw" class="w-3 h-3 mr-1" />Refresh
      </Button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { frappeRequest } from 'frappe-ui'

const API = 'ups_worklist_portal.api.ups_actions'

defineEmits(['close'])

const items        = ref([])
const loading      = ref(false)
const error        = ref(null)
const processingUid = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  error.value   = null
  try {
    const r = await frappeRequest({
      url: '/api/method/' + API + '.get_reconciliation_diff',
    })
    items.value = Array.isArray(r) ? r : []
  } catch (e) {
    error.value = 'Failed to load reconciliation: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
}

async function accept(uid, action) {
  processingUid.value = uid
  try {
    await frappeRequest({
      url: '/api/method/' + API + '.accept_reconciliation_item',
      params: { ups_uid: uid, action },
    })
    await load()
  } catch (e) {
    alert('Error: ' + (e?.message || e))
  } finally {
    processingUid.value = null
  }
}
</script>
