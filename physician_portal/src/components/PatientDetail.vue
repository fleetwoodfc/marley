<template>
	<Dialog v-model="show" :options="{ size: '6xl' }">
		<template #body-title>
			<h2 class="text-xl font-semibold text-gray-900">Patient Details</h2>
		</template>
		<template #body-content>
			<div v-if="loading" class="flex items-center justify-center py-12">
				<span class="text-gray-500">Loading...</span>
			</div>
			<div v-else-if="detail" class="space-y-6">
				<!-- Patient Header -->
				<div class="p-4 bg-white rounded-xl shadow-sm border">
					<div class="flex items-center gap-4">
						<img
							v-if="detail.patient.image"
							:src="detail.patient.image"
							class="w-16 h-16 rounded-full object-cover border"
						/>
						<div
							v-else
							class="w-16 h-16 rounded-full flex items-center justify-center
								bg-gray-100 text-gray-600 font-bold text-xl border"
						>
							{{ detail.patient.patient_name?.charAt(0)?.toUpperCase() }}
						</div>
						<div class="flex-1">
							<h2 class="text-lg font-semibold text-gray-900">
								{{ detail.patient.patient_name }}
							</h2>
							<div class="flex gap-4 text-sm text-gray-600 mt-1">
								<span v-if="detail.patient.uid">MRN: {{ detail.patient.uid }}</span>
								<span v-if="detail.patient.sex">{{ detail.patient.sex }}</span>
								<span v-if="detail.patient.dob">DOB: {{ formatDate(detail.patient.dob) }}</span>
								<span v-if="detail.patient.blood_group">Blood: {{ detail.patient.blood_group }}</span>
							</div>
							<div class="flex gap-4 text-sm text-gray-500 mt-1">
								<span v-if="detail.patient.email">
									<FeatherIcon name="mail" class="inline w-3 h-3 mr-1" />
									{{ detail.patient.email }}
								</span>
								<span v-if="detail.patient.mobile">
									<FeatherIcon name="phone" class="inline w-3 h-3 mr-1" />
									{{ detail.patient.mobile }}
								</span>
							</div>
						</div>
						<Button variant="solid" @click="$emit('create-order', detail.patient.name)">
							<template #prefix>
								<FeatherIcon name="plus" class="h-4" />
							</template>
							New Order
						</Button>
					</div>
				</div>

				<!-- Recent Appointments -->
				<div>
					<h3 class="text-md font-semibold text-gray-800 mb-2">Recent Appointments</h3>
					<div v-if="detail.appointments && detail.appointments.length" class="space-y-2">
						<div
							v-for="appt in detail.appointments"
							:key="appt.name"
							class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border"
						>
							<div>
								<p class="text-sm font-medium text-gray-800">
									{{ appt.practitioner_name || appt.practitioner }}
								</p>
								<p class="text-xs text-gray-500">
									{{ formatDate(appt.appointment_date) }}
									&middot; {{ appt.appointment_time }}
									<span v-if="appt.duration"> ({{ appt.duration }} mins)</span>
								</p>
							</div>
							<Badge :variant="'outline'" :theme="getStatusColor(appt.status)">
								{{ appt.status }}
							</Badge>
						</div>
					</div>
					<p v-else class="text-sm text-gray-500">No recent appointments.</p>
				</div>

				<!-- Recent Orders -->
				<div>
					<h3 class="text-md font-semibold text-gray-800 mb-2">Recent Orders</h3>
					<div v-if="detail.orders && detail.orders.length" class="space-y-2">
						<div
							v-for="order in detail.orders"
							:key="order.name"
							class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border"
						>
							<div>
								<p class="text-sm font-medium text-gray-800">
									{{ order.template_dn || order.order_description || order.name }}
								</p>
								<p class="text-xs text-gray-500">
									{{ order.template_dt }}
									&middot; {{ formatDate(order.order_date) }}
								</p>
							</div>
							<div class="flex items-center gap-2">
								<Badge v-if="order.billing_status" :variant="'outline'" size="sm"
									:theme="getStatusColor(order.billing_status)">
									{{ order.billing_status }}
								</Badge>
								<Badge :variant="'outline'" :theme="getStatusColor(order.status)">
									{{ order.status }}
								</Badge>
							</div>
						</div>
					</div>
					<p v-else class="text-sm text-gray-500">No recent orders.</p>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { createResource, Dialog } from 'frappe-ui'
import { formatDate, getStatusColor } from '@/utils/formatters'

const props = defineProps({
	modelValue: Boolean,
	patient: Object,
})

const emit = defineEmits(['update:modelValue', 'create-order'])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit('update:modelValue', val),
})

const detail = ref(null)
const loading = ref(false)

const fetchDetail = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_patient_detail',
	method: 'GET',
	onSuccess(response) {
		detail.value = response
		loading.value = false
	},
	onError() {
		loading.value = false
	},
})

watch(() => props.patient, (p) => {
	if (p && p.name) {
		loading.value = true
		detail.value = null
		fetchDetail.fetch({ patient: p.name })
	}
}, { immediate: true })
</script>
