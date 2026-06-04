<template>
	<div class="space-y-4">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-gray-800">Diagnostic Orders</h2>
			<Button variant="solid" @click="$emit('create-order')">
				<template #prefix>
					<FeatherIcon name="plus" class="h-4" />
				</template>
				New Order
			</Button>
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
				<option value="Draft">Draft</option>
				<option value="Active">Active</option>
				<option value="On Hold">On Hold</option>
				<option value="Completed">Completed</option>
				<option value="Revoked">Revoked</option>
			</select>
		</div>

		<!-- Loading -->
		<div v-if="orders.loading" class="flex items-center justify-center py-8">
			<span class="text-gray-500">Loading orders...</span>
		</div>

		<!-- Empty State -->
		<div
			v-else-if="!orderData.data?.length"
			class="text-center py-12 bg-white rounded-xl border border-dashed border-gray-300"
		>
			<FeatherIcon name="clipboard" class="mx-auto h-10 w-10 text-gray-400 mb-3" />
			<p class="text-gray-500 text-sm">No orders found.</p>
		</div>

		<!-- Order Cards -->
		<div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
			<Card
				v-for="order in orderData.data"
				:key="order.name"
				class="cursor-pointer hover:shadow-md transition-shadow"
				@click="$emit('view-order', order)"
			>
				<div class="p-4 space-y-2">
					<div class="flex items-start justify-between">
						<div class="flex-1 min-w-0">
							<h3 class="text-sm font-semibold text-gray-900 truncate">
								{{ order.template_dn || order.order_description || order.name }}
							</h3>
							<p class="text-xs text-gray-500 mt-0.5">
								{{ order.template_dt || 'Service Request' }}
							</p>
						</div>
						<Badge :variant="'outline'" :theme="getStatusColor(order.status)">
							{{ order.status }}
						</Badge>
					</div>
					<div class="flex items-center gap-3 text-xs text-gray-600">
						<span>
							<FeatherIcon name="user" class="inline w-3 h-3 mr-1" />
							{{ order.patient_name || order.patient }}
						</span>
						<span v-if="order.order_date">
							<FeatherIcon name="calendar" class="inline w-3 h-3 mr-1" />
							{{ formatDate(order.order_date) }}
						</span>
					</div>
					<div v-if="order.priority" class="text-xs">
						<Badge size="sm" :variant="'subtle'"
							:theme="order.priority === 'Urgent' || order.priority === 'Stat' ? 'red' : 'gray'">
							{{ order.priority }}
						</Badge>
					</div>
					<!-- Edit button for Draft orders -->
					<div v-if="order.status === 'Draft'" class="pt-1" @click.stop>
						<Button
							size="sm"
							variant="outline"
							@click.stop="$emit('edit-order', order)"
						>
							<template #prefix>
								<FeatherIcon name="edit-2" class="h-3 w-3" />
							</template>
							Edit
						</Button>
					</div>
				</div>
			</Card>
		</div>

		<!-- Pagination -->
		<div
			v-if="orderData.total && orderData.total > pageSize"
			class="flex items-center justify-between pt-2"
		>
			<p class="text-sm text-gray-500">
				Showing {{ (page - 1) * pageSize + 1 }}-{{ Math.min(page * pageSize, orderData.total) }}
				of {{ orderData.total }}
			</p>
			<div class="flex gap-2">
				<Button size="sm" :disabled="page <= 1" @click="page--">Previous</Button>
				<Button size="sm" :disabled="page * pageSize >= orderData.total" @click="page++">Next</Button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, watch, computed, reactive } from 'vue'
import { createResource, Card } from 'frappe-ui'
import { formatDate, getStatusColor } from '@/utils/formatters'

const props = defineProps({
	selectedPatient: String,
})

const emit = defineEmits(['view-order', 'create-order', 'edit-order'])

const search = ref('')
const statusFilter = ref('')
const page = ref(1)
const pageSize = 12

const orderData = reactive({ data: [], total: 0 })

const orders = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_orders',
	method: 'GET',
	onSuccess(response) {
		orderData.data = response.orders || response.data || []
		orderData.total = response.total || 0
	},
})

let searchTimeout = null
watch([search, statusFilter], () => {
	clearTimeout(searchTimeout)
	searchTimeout = setTimeout(() => {
		page.value = 1
		fetchOrders()
	}, 300)
})

watch(page, fetchOrders)

function fetchOrders() {
	const params = {
		page: page.value,
		page_size: pageSize,
	}
	if (search.value) params.patient = search.value
	if (statusFilter.value) params.status = statusFilter.value
	if (props.selectedPatient) params.patient = props.selectedPatient
	orders.fetch(params)
}

// Initial load
fetchOrders()

defineExpose({ refresh: fetchOrders })
</script>
