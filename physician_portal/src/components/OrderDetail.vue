<template>
	<Dialog v-model="show" :options="{ size: '4xl' }">
		<template #body-title>
			<h2 class="text-xl font-semibold text-gray-900">Order Details</h2>
		</template>
		<template #body-content>
			<div v-if="loading" class="flex items-center justify-center py-12">
				<span class="text-gray-500">Loading...</span>
			</div>
			<div v-else-if="detail" class="space-y-5">
				<!-- Order Header -->
				<div class="p-4 bg-white rounded-xl shadow-sm border">
					<div class="flex items-start justify-between">
						<div>
							<h3 class="text-lg font-semibold text-gray-900">
								{{ detail.template_dn || detail.order_description || detail.name }}
							</h3>
							<p class="text-sm text-gray-500 mt-1">
								{{ detail.template_dt || 'Service Request' }}
								&middot; {{ detail.name }}
							</p>
						</div>
						<Badge :variant="'outline'" :theme="getStatusColor(detail.status)" size="lg">
							{{ detail.status }}
						</Badge>
					</div>
				</div>

				<!-- Key Info Grid -->
				<div class="grid grid-cols-2 gap-4">
					<InfoRow label="Patient" :value="detail.patient_name || detail.patient" />
					<InfoRow label="Practitioner" :value="detail.practitioner_name || detail.practitioner" />
					<InfoRow label="Order Date" :value="formatDate(detail.order_date)" />
					<InfoRow label="Priority" :value="detail.priority" />
					<InfoRow label="Intent" :value="detail.intent" />
					<InfoRow label="Billing Status" :value="detail.billing_status" />
					<InfoRow
						v-if="detail.occurrence_date"
						label="Scheduled Date"
						:value="formatDate(detail.occurrence_date)"
					/>
					<InfoRow
						v-if="detail.occurrence_time"
						label="Scheduled Time"
						:value="detail.occurrence_time"
					/>
				</div>

				<!-- Template Information -->
				<div v-if="detail.template_info" class="p-4 bg-gray-50 rounded-lg border">
					<h4 class="text-sm font-semibold text-gray-700 mb-2">Template Information</h4>
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div v-for="(value, key) in detail.template_info" :key="key">
							<span class="text-gray-500">{{ formatLabel(key) }}:</span>
							<span class="ml-1 text-gray-800">{{ value }}</span>
						</div>
					</div>
				</div>

				<!-- Clinical Question / Notes -->
				<div v-if="detail.order_description" class="p-4 bg-gray-50 rounded-lg border">
					<h4 class="text-sm font-semibold text-gray-700 mb-1">Clinical Question / Notes</h4>
					<p class="text-sm text-gray-800 whitespace-pre-wrap">{{ detail.order_description }}</p>
				</div>
			</div>
		</template>
		<template #actions>
			<Button
				v-if="detail && detail.docstatus === 0"
				variant="solid"
				@click="onEditOrder"
			>
				<template #prefix>
					<FeatherIcon name="edit-2" class="h-4" />
				</template>
				Edit Order
			</Button>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch, computed, h } from 'vue'
import { createResource, Dialog } from 'frappe-ui'
import { formatDate, getStatusColor } from '@/utils/formatters'

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
	orderName: String,
})

const emit = defineEmits(['update:modelValue', 'edit-order'])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit('update:modelValue', val),
})

const detail = ref(null)
const loading = ref(false)

const fetchDetail = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_order_detail',
	method: 'GET',
	onSuccess(response) {
		detail.value = response
		loading.value = false
	},
	onError() {
		loading.value = false
	},
})

watch(() => props.orderName, (name) => {
	if (name) {
		loading.value = true
		detail.value = null
		fetchDetail.fetch({ order_name: name })
	}
}, { immediate: true })

function formatLabel(key) {
	return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function onEditOrder() {
	show.value = false
	emit('edit-order', props.orderName)
}
</script>
