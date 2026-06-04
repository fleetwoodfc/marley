<template>
	<div class="space-y-4">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-gray-800">Imaging Service Requests</h2>
		</div>

		<!-- Filters -->
		<div class="flex gap-3">
			<div class="flex-1">
				<input
					v-model="search"
					type="text"
					placeholder="Filter by patient..."
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
				<option value="Draft">Draft</option>
				<option value="Ordered">Ordered</option>
				<option value="In Progress">In Progress</option>
				<option value="Completed">Completed</option>
				<option value="Cancelled">Cancelled</option>
			</select>
		</div>

		<!-- Loading -->
		<div v-if="isrs.loading" class="flex items-center justify-center py-8">
			<span class="text-gray-500">Loading imaging requests...</span>
		</div>

		<!-- Empty State -->
		<div
			v-else-if="!isrData.data?.length"
			class="text-center py-12 bg-white rounded-xl border border-dashed border-gray-300"
		>
			<FeatherIcon name="image" class="mx-auto h-10 w-10 text-gray-400 mb-3" />
			<p class="text-gray-500 text-sm">No imaging service requests found.</p>
		</div>

		<!-- ISR Cards -->
		<div v-else class="space-y-3">
			<Card
				v-for="isr in isrData.data"
				:key="isr.name"
				class="hover:shadow-md transition-shadow"
			>
				<div class="p-4 space-y-3">
					<!-- ISR Header -->
					<div class="flex items-start justify-between">
						<div>
							<h3 class="text-sm font-semibold text-gray-900">
								{{ isr.name }}
							</h3>
							<div class="flex items-center gap-3 text-xs text-gray-600 mt-1">
								<span>
									<FeatherIcon name="user" class="inline w-3 h-3 mr-1" />
									{{ isr.patient_name || isr.patient }}
								</span>
								<span v-if="isr.referring_practitioner">
									<FeatherIcon name="stethoscope" class="inline w-3 h-3 mr-1" />
									{{ isr.referring_practitioner }}
								</span>
								<span v-if="isr.order_date">
									<FeatherIcon name="calendar" class="inline w-3 h-3 mr-1" />
									{{ formatDate(isr.order_date) }}
								</span>
							</div>
						</div>
							<Badge :variant="'outline'" :theme="getStatusColor(isr.status || 'Draft')">
								{{ isr.status || 'Draft' }}
						</Badge>
					</div>

					<!-- Requested Procedures -->
					<div v-if="isr.requested_procedures && isr.requested_procedures.length">
						<p class="text-xs font-semibold text-gray-500 mb-1 uppercase tracking-wider">
							Requested Procedures ({{ isr.requested_procedures.length }})
						</p>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-2">
							<div
								v-for="rp in isr.requested_procedures"
								:key="rp.name"
								class="flex items-center justify-between p-2 bg-gray-50 rounded-lg border text-sm"
							>
								<div class="flex-1 min-w-0">
									<p class="font-medium text-gray-800 truncate">
										{{ rp.procedure || rp.name }}
									</p>
									<div class="flex gap-2 text-xs text-gray-500 mt-0.5">
										<span v-if="rp.modality">{{ rp.modality }}</span>
										<span v-if="rp.body_part">{{ rp.body_part }}</span>
									</div>
								</div>
								<Badge
									v-if="rp.status"
									size="sm"
									:variant="'outline'"
									:theme="getStatusColor(rp.status)"
								>
									{{ rp.status }}
								</Badge>
							</div>
						</div>
					</div>
				</div>
			</Card>
		</div>

		<!-- Pagination -->
		<div
			v-if="isrData.total && isrData.total > pageSize"
			class="flex items-center justify-between pt-2"
		>
			<p class="text-sm text-gray-500">
				Showing {{ (page - 1) * pageSize + 1 }}-{{ Math.min(page * pageSize, isrData.total) }}
				of {{ isrData.total }}
			</p>
			<div class="flex gap-2">
				<Button size="sm" :disabled="page <= 1" @click="page--">Previous</Button>
				<Button size="sm" :disabled="page * pageSize >= isrData.total" @click="page++">Next</Button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, watch, reactive } from 'vue'
import { createResource, Card } from 'frappe-ui'
import { formatDate, getStatusColor } from '@/utils/formatters'

const search = ref('')
const statusFilter = ref('')
const page = ref(1)
const pageSize = 10

const isrData = reactive({ data: [], total: 0 })

const isrs = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_imaging_service_requests',
	method: 'GET',
	onSuccess(response) {
		isrData.data = response.requests || response.data || []
		isrData.total = response.total || 0
	},
})

let searchTimeout = null
watch([search, statusFilter], () => {
	clearTimeout(searchTimeout)
	searchTimeout = setTimeout(() => {
		page.value = 1
		fetchISRs()
	}, 300)
})

watch(page, fetchISRs)

function fetchISRs() {
	const params = {
		page: page.value,
		page_size: pageSize,
	}
	if (search.value) params.patient = search.value
	if (statusFilter.value) params.status = statusFilter.value
	isrs.fetch(params)
}

// Initial load
fetchISRs()

defineExpose({ refresh: fetchISRs })
</script>
