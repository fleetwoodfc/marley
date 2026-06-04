<template>
	<Dialog v-model="show" :options="{ size: '5xl' }">
		<template #body-title>
			<h2 class="text-xl font-semibold text-gray-900">Diagnostic Report</h2>
		</template>
		<template #body-content>
			<div v-if="loading" class="flex items-center justify-center py-12">
				<span class="text-gray-500">Loading...</span>
			</div>
			<div v-else-if="detail" class="space-y-5 max-h-[70vh] overflow-y-auto">
				<!-- Report Header -->
				<div class="p-4 bg-white rounded-xl shadow-sm border">
					<div class="flex items-start justify-between">
						<div>
							<h3 class="text-lg font-semibold text-gray-900">
								{{ detail.patient_name || detail.patient }}
							</h3>
							<p class="text-sm text-gray-500 mt-1">
								{{ detail.name }}
								<span v-if="detail.gender || detail.age" class="ml-2">
									&middot;
									<span v-if="detail.gender">{{ detail.gender }}</span>
									<span v-if="detail.gender && detail.age">, </span>
									<span v-if="detail.age">{{ detail.age }}</span>
								</span>
							</p>
						</div>
						<Badge :variant="'outline'" :theme="getStatusColor(detail.status)" size="lg">
							{{ detail.status }}
						</Badge>
					</div>

					<!-- Status Action Bar -->
					<div
						v-if="allowedTransitions.length"
						class="mt-4 pt-3 border-t flex items-center gap-3"
					>
						<span class="text-sm text-gray-500">Change status:</span>
						<button
							v-for="target in allowedTransitions"
							:key="target"
							class="inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-lg border transition-colors disabled:opacity-50"
							:class="statusButtonClass(target)"
							:disabled="updating"
							@click="confirmStatusChange(target)"
						>
							{{ target }}
						</button>
					</div>

					<!-- Confirmation Banner -->
					<div
						v-if="pendingStatus"
						class="mt-3 p-3 rounded-lg border flex items-center justify-between"
						:class="pendingStatus === 'Approved'
							? 'bg-green-50 border-green-200'
							: pendingStatus === 'Rejected'
								? 'bg-red-50 border-red-200'
								: 'bg-blue-50 border-blue-200'"
					>
						<p class="text-sm">
							<span class="font-medium">{{ confirmMessage }}</span>
						</p>
						<div class="flex gap-2 ml-4 shrink-0">
							<button
								class="px-3 py-1 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50"
								@click="pendingStatus = null"
							>
								Cancel
							</button>
							<button
								class="px-3 py-1 text-sm rounded text-white"
								:class="pendingStatus === 'Rejected' ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'"
								:disabled="updating"
								@click="executeStatusChange"
							>
								{{ updating ? 'Updating...' : 'Confirm' }}
							</button>
						</div>
					</div>
				</div>

				<!-- Key Info Grid -->
				<div class="grid grid-cols-2 gap-4">
					<InfoRow label="Patient" :value="detail.patient_name || detail.patient" />
					<InfoRow label="Practitioner" :value="detail.practitioner_name || detail.practitioner" />
					<InfoRow label="Created" :value="formatDateTime(detail.creation)" />
					<InfoRow label="Last Modified" :value="formatDateTime(detail.modified)" />
				</div>

				<!-- Observations -->
				<div v-if="detail.observations && detail.observations.length">
					<h4 class="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wider">
						Observations ({{ detail.observations.length }})
					</h4>
					<div class="space-y-3">
						<div
							v-for="obs in detail.observations"
							:key="obs.name"
							class="border rounded-lg bg-white overflow-hidden"
						>
							<!-- Observation Header -->
							<div class="p-3 flex items-start justify-between bg-gray-50 border-b">
								<div>
									<p class="text-sm font-semibold text-gray-900">
										{{ obs.template || obs.name }}
									</p>
									<div class="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
										<span v-if="obs.category">
											<Badge size="sm" variant="subtle" :theme="getCategoryColor(obs.category)">
												{{ obs.category }}
											</Badge>
										</span>
										<span v-if="obs.posting_date">{{ formatDate(obs.posting_date) }}</span>
										<span v-if="obs.practitioner">by {{ obs.practitioner }}</span>
									</div>
								</div>
								<Badge :variant="'outline'" :theme="getStatusColor(obs.status)" size="sm">
									{{ obs.status }}
								</Badge>
							</div>

							<!-- Observation Result (simple) -->
							<div v-if="!obs.components || !obs.components.length" class="p-3">
								<div v-if="obs.result !== null && obs.result !== undefined && obs.result !== ''" class="flex items-baseline gap-2">
									<span class="text-sm font-medium text-gray-900">
										{{ formatResult(obs) }}
									</span>
									<span v-if="obs.unit" class="text-xs text-gray-500">{{ obs.unit }}</span>
								</div>
								<p v-else class="text-sm text-gray-400 italic">No result recorded</p>
								<p v-if="obs.reference_range" class="text-xs text-gray-500 mt-1">
									Reference: {{ obs.reference_range }}
								</p>
								<div
									v-if="obs.note"
									class="mt-2 text-xs text-gray-600 bg-yellow-50 p-2 rounded border border-yellow-200"
								>
									{{ obs.note }}
								</div>
							</div>

							<!-- Observation Components (panel/group) -->
							<div v-else class="divide-y">
								<div
									v-for="comp in obs.components"
									:key="comp.name"
									class="px-3 py-2 flex items-center justify-between"
								>
									<div class="flex-1 min-w-0">
										<p class="text-sm text-gray-800">{{ comp.template || comp.name }}</p>
									</div>
									<div class="flex items-center gap-3 text-sm">
										<span v-if="comp.result !== null && comp.result !== undefined && comp.result !== ''"
											class="font-medium text-gray-900">
											{{ formatComponentResult(comp) }}
										</span>
										<span v-else class="text-gray-400 italic text-xs">—</span>
										<span v-if="comp.unit" class="text-xs text-gray-500 w-12 text-right">{{ comp.unit }}</span>
										<span v-if="comp.reference_range" class="text-xs text-gray-400 w-24 text-right">
											{{ comp.reference_range }}
										</span>
										<Badge :variant="'outline'" :theme="getStatusColor(comp.status)" size="sm">
											{{ comp.status }}
										</Badge>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- No Observations -->
				<div
					v-else
					class="text-center py-8 bg-gray-50 rounded-lg border border-dashed border-gray-300"
				>
					<FeatherIcon name="activity" class="mx-auto h-8 w-8 text-gray-400 mb-2" />
					<p class="text-sm text-gray-500">No observations recorded for this patient.</p>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch, computed, h } from 'vue'
import { createResource, Dialog } from 'frappe-ui'
import { formatDate, formatDateTime, getStatusColor } from '@/utils/formatters'

const InfoRow = (props) => {
	if (!props.value) return null
	return h('div', { class: 'flex flex-col' }, [
		h('span', { class: 'text-xs text-gray-500' }, props.label),
		h('span', { class: 'text-sm font-medium text-gray-800' }, props.value),
	])
}
InfoRow.props = ['label', 'value']

const props = defineProps({
	modelValue: Boolean,
	reportName: String,
})

const emit = defineEmits(['update:modelValue', 'status-changed'])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit('update:modelValue', val),
})

const detail = ref(null)
const loading = ref(false)
const updating = ref(false)
const pendingStatus = ref(null)
const allowedTransitions = ref([])

const fetchDetail = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_diagnostic_report_detail',
	method: 'GET',
	onSuccess(response) {
		detail.value = response
		loading.value = false
		fetchTransitions()
	},
	onError() {
		loading.value = false
	},
})

const fetchTransitionsResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_allowed_status_transitions',
	method: 'GET',
	onSuccess(response) {
		allowedTransitions.value = response.allowed || []
	},
	onError() {
		allowedTransitions.value = []
	},
})

function fetchTransitions() {
	if (props.reportName) {
		fetchTransitionsResource.fetch({ report_name: props.reportName })
	}
}

const updateStatusResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.update_diagnostic_report_status',
	method: 'POST',
	onSuccess(response) {
		updating.value = false
		pendingStatus.value = null
		// Update local state
		if (detail.value) {
			detail.value.status = response.status
		}
		// Refresh transitions for new status
		fetchTransitions()
		// Re-fetch detail to get updated observation statuses
		fetchDetail.fetch({ report_name: props.reportName })
		// Notify parent to refresh the list
		emit('status-changed', { name: response.name, status: response.status })
	},
	onError(err) {
		updating.value = false
		pendingStatus.value = null
		console.error('Status update failed:', err)
	},
})

const confirmMessage = computed(() => {
	if (!pendingStatus.value) return ''
	if (pendingStatus.value === 'Approved') {
		return 'Approve this report? Linked observations with results will be submitted.'
	}
	if (pendingStatus.value === 'Rejected') {
		return 'Reject this report? Approved observations will be cancelled.'
	}
	return `Change status to "${pendingStatus.value}"?`
})

function confirmStatusChange(target) {
	// For Approved/Rejected show confirmation; others change directly
	if (target === 'Approved' || target === 'Rejected') {
		pendingStatus.value = target
	} else {
		pendingStatus.value = null
		doUpdate(target)
	}
}

function executeStatusChange() {
	if (pendingStatus.value) {
		doUpdate(pendingStatus.value)
	}
}

function doUpdate(status) {
	updating.value = true
	updateStatusResource.submit({ report_name: props.reportName, status })
}

function statusButtonClass(target) {
	switch (target) {
		case 'Approved':
			return 'border-green-300 text-green-700 bg-green-50 hover:bg-green-100'
		case 'Rejected':
			return 'border-red-300 text-red-700 bg-red-50 hover:bg-red-100'
		case 'Pending Review':
			return 'border-yellow-300 text-yellow-700 bg-yellow-50 hover:bg-yellow-100'
		case 'Open':
			return 'border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100'
		default:
			return 'border-gray-300 text-gray-700 bg-gray-50 hover:bg-gray-100'
	}
}

watch(() => props.reportName, (name) => {
	if (name) {
		loading.value = true
		detail.value = null
		pendingStatus.value = null
		allowedTransitions.value = []
		fetchDetail.fetch({ report_name: name })
	}
}, { immediate: true })

function getCategoryColor(category) {
	switch (category) {
		case 'Laboratory': return 'blue'
		case 'Imaging': return 'purple'
		case 'Vital Signs': return 'green'
		case 'Procedure': return 'orange'
		case 'Social History': return 'gray'
		default: return 'gray'
	}
}

function formatResult(obs) {
	if (obs.data_type === 'Quantity' && obs.result !== null) {
		return String(obs.result)
	}
	if (obs.data_type === 'Boolean') {
		return obs.result === 'Yes' || obs.result === '1' || obs.result === true ? 'Positive' : 'Negative'
	}
	return String(obs.result || '')
}

function formatComponentResult(comp) {
	if (comp.data_type === 'Quantity' && comp.result !== null) {
		return String(comp.result)
	}
	if (comp.data_type === 'Boolean') {
		return comp.result === 'Yes' || comp.result === '1' || comp.result === true ? 'Positive' : 'Negative'
	}
	return String(comp.result || '')
}
</script>
