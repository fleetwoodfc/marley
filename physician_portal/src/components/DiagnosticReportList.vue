<template>
	<div class="space-y-4">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-gray-800">Diagnostic Reports</h2>
		</div>

		<!-- Filters -->
		<div class="flex gap-3">
			<div class="flex-1">
				<input
					v-model="search"
					type="text"
					placeholder="Filter by patient name..."
					class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
						focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
				/>
			</div>
			<select
				v-model="statusFilter"
				class="rounded-lg border border-gray-300 px-3 py-2 text-sm
					focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
			>
				<option value="">All Statuses</option>
				<option value="Open">Open</option>
				<option value="Pending Review">Pending Review</option>
				<option value="Partially Approved">Partially Approved</option>
				<option value="Approved">Approved</option>
				<option value="Rejected">Rejected</option>
			</select>
		</div>

		<!-- Loading -->
		<div v-if="reports.loading" class="flex items-center justify-center py-8">
			<span class="text-gray-500">Loading reports...</span>
		</div>

		<!-- Empty State -->
		<div
			v-else-if="!reportData.data?.length"
			class="text-center py-12 bg-white rounded-xl border border-dashed border-gray-300"
		>
			<FeatherIcon name="file-text" class="mx-auto h-10 w-10 text-gray-400 mb-3" />
			<p class="text-gray-500 text-sm">No diagnostic reports found.</p>
		</div>

		<!-- Report Cards -->
		<div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
			<Card
				v-for="report in reportData.data"
				:key="report.name"
				class="cursor-pointer hover:shadow-md transition-shadow"
				@click="$emit('view-report', report)"
			>
				<div class="p-4 space-y-2">
					<div class="flex items-start justify-between">
						<div class="flex-1 min-w-0">
							<h3 class="text-sm font-semibold text-gray-900 truncate">
								{{ report.patient_name || report.patient }}
							</h3>
							<p class="text-xs text-gray-500 mt-0.5">
								{{ report.name }}
							</p>
						</div>
						<Badge :variant="'outline'" :theme="getStatusColor(report.status)">
							{{ report.status }}
						</Badge>
					</div>
					<div class="flex items-center gap-3 text-xs text-gray-600">
						<span v-if="report.practitioner_name || report.practitioner_display">
							<FeatherIcon name="user" class="inline w-3 h-3 mr-1" />
							{{ report.practitioner_name || report.practitioner_display }}
						</span>
						<span v-if="report.creation">
							<FeatherIcon name="calendar" class="inline w-3 h-3 mr-1" />
							{{ formatDate(report.creation) }}
						</span>
					</div>
					<div v-if="report.gender || report.age" class="text-xs text-gray-500">
						<span v-if="report.gender">{{ report.gender }}</span>
						<span v-if="report.gender && report.age"> &middot; </span>
						<span v-if="report.age">{{ report.age }}</span>
					</div>
				</div>
			</Card>
		</div>

		<!-- Pagination -->
		<div
			v-if="reportData.total && reportData.total > pageSize"
			class="flex items-center justify-between pt-2"
		>
			<p class="text-sm text-gray-500">
				Showing {{ (page - 1) * pageSize + 1 }}-{{ Math.min(page * pageSize, reportData.total) }}
				of {{ reportData.total }}
			</p>
			<div class="flex gap-2">
				<Button size="sm" :disabled="page <= 1" @click="page--">Previous</Button>
				<Button size="sm" :disabled="page * pageSize >= reportData.total" @click="page++">Next</Button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, watch, reactive } from 'vue'
import { createResource, Card } from 'frappe-ui'
import { formatDate, getStatusColor } from '@/utils/formatters'

const props = defineProps({
	selectedPatient: String,
})

const emit = defineEmits(['view-report'])

const search = ref('')
const statusFilter = ref('')
const page = ref(1)
const pageSize = 12

const reportData = reactive({ data: [], total: 0 })

const reports = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_diagnostic_reports',
	method: 'GET',
	onSuccess(response) {
		reportData.data = response.reports || response.data || []
		reportData.total = response.total || 0
	},
})

let searchTimeout = null
watch([search, statusFilter], () => {
	clearTimeout(searchTimeout)
	searchTimeout = setTimeout(() => {
		page.value = 1
		fetchReports()
	}, 300)
})

watch(page, fetchReports)

function fetchReports() {
	const params = {
		page: page.value,
		page_size: pageSize,
	}
	if (search.value) params.patient = search.value
	if (statusFilter.value) params.status = statusFilter.value
	if (props.selectedPatient) params.patient = props.selectedPatient
	reports.fetch(params)
}

// Initial load
fetchReports()

defineExpose({ refresh: fetchReports })
</script>
