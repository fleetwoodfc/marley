<template>
	<Dialog v-model="show" :options="{ size: '4xl' }">
		<template #body-title>
			<h2 class="text-xl font-semibold text-gray-900">
				{{ isEditMode ? 'Edit Draft Order' : 'Create Diagnostic Order' }}
			</h2>
		</template>
		<template #body-content>
			<div class="space-y-4">
				<!-- Patient Selector -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-1">Patient *</label>
					<!-- Read-only in edit mode -->
					<div v-if="isEditMode || preselectedPatient" class="flex items-center gap-2">
						<span class="text-sm font-medium text-gray-900 bg-gray-100 px-3 py-2 rounded-lg flex-1">
							{{ editPatientName || preselectedPatient }}
						</span>
						<Button v-if="!isEditMode" size="sm" variant="ghost" @click="$emit('update:patient', null); selectedPatient = ''">
							Change
						</Button>
					</div>
					<div v-else>
						<input
							v-model="patientSearch"
							type="text"
							placeholder="Search patients..."
							class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
								focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
							@input="searchPatients"
						/>
						<div
							v-if="patientOptions.length"
							class="mt-1 border border-gray-200 rounded-lg bg-white shadow-lg max-h-40 overflow-y-auto"
						>
							<div
								v-for="p in patientOptions"
								:key="p.name"
								class="px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer"
								@click="selectPatient(p)"
							>
								{{ p.patient_name }} ({{ p.name }})
							</div>
						</div>
					</div>
				</div>

				<!-- Template Type -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-1">Order Type *</label>
					<select
						v-model="templateType"
						class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
							focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
						@change="templateSearch = ''; templateOptions = []; selectedTemplate = null"
					>
						<option value="">Select type...</option>
						<option value="Radiology Procedure Template">Radiology</option>
						<option value="Lab Test Template">Lab Test</option>
						<option value="Clinical Procedure Template">Clinical Procedure</option>
						<option value="Observation Template">Observation</option>
					</select>
				</div>

				<!-- Template Selector -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-1">Order Template *</label>
					<input
						v-model="templateSearch"
						type="text"
						:placeholder="templateType ? 'Search templates...' : 'Select order type first'"
						:disabled="!templateType"
						class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
							focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none
							disabled:bg-gray-100 disabled:text-gray-400"
						@input="searchTemplates"
					/>
					<div v-if="selectedTemplate" class="mt-1 text-xs text-green-600 flex items-center gap-1">
						<FeatherIcon name="check-circle" class="w-3 h-3" />
						Selected: {{ selectedTemplate.name }}
					</div>
					<div
						v-if="templateOptions.length && !selectedTemplate"
						class="mt-1 border border-gray-200 rounded-lg bg-white shadow-lg max-h-40 overflow-y-auto"
					>
						<div
							v-for="t in templateOptions"
							:key="t.name"
							class="px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer"
							@click="selectTemplate(t)"
						>
							{{ t.name }}
							<span v-if="t.description" class="text-xs text-gray-400 ml-1">
								- {{ t.description }}
							</span>
						</div>
					</div>
				</div>

				<!-- Priority -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-1">Priority</label>
					<select
						v-model="priority"
						class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
							focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
					>
						<option value="Routine-Priority">Routine</option>
						<option value="Urgent-Priority">Urgent</option>
						<option value="ASAP-Priority">ASAP</option>
						<option value="STAT-Priority">Stat</option>
					</select>
				</div>

				<!-- Occurrence Date/Time -->
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="block text-sm font-medium text-gray-700 mb-1">Scheduled Date</label>
						<input
							v-model="occurrenceDate"
							type="date"
							class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
								focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
						/>
					</div>
					<div>
						<label class="block text-sm font-medium text-gray-700 mb-1">Scheduled Time</label>
						<input
							v-model="occurrenceTime"
							type="time"
							class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
								focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
						/>
					</div>
				</div>

				<!-- Clinical Question -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-1">Clinical Question / Notes</label>
					<textarea
						v-model="clinicalQuestion"
						rows="3"
						placeholder="Describe the clinical question or reason for the order..."
						class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
							focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none resize-none"
					></textarea>
				</div>

				<!-- Submit Toggle -->
				<div class="flex items-center gap-2">
					<input type="checkbox" id="submitOrder" v-model="submitOrder" class="rounded border-gray-300" />
					<label for="submitOrder" class="text-sm text-gray-700">
						{{ isEditMode ? 'Submit order after saving' : 'Submit order immediately' }}
					</label>
				</div>

				<!-- Error -->
				<div v-if="error" class="p-3 bg-red-50 rounded-lg border border-red-200">
					<p class="text-sm text-red-600">{{ error }}</p>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="solid" :loading="creating" @click="isEditMode ? saveOrder() : createOrder()">
				{{ isEditMode ? 'Save Changes' : 'Create Order' }}
			</Button>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { createResource, Dialog } from 'frappe-ui'

const props = defineProps({
	modelValue: Boolean,
	patient: String,
	orderName: String,  // when set, component operates in edit mode
})

const emit = defineEmits(['update:modelValue', 'order-created', 'order-updated'])

const isEditMode = computed(() => !!props.orderName)
const editPatientName = ref('')  // display name for the locked patient in edit mode

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit('update:modelValue', val),
})

const preselectedPatient = computed(() => props.patient)

// Form state
const selectedPatient = ref('')
const patientSearch = ref('')
const patientOptions = ref([])
const templateType = ref('')
const templateSearch = ref('')
const templateOptions = ref([])
const selectedTemplate = ref(null)
const priority = ref('Routine-Priority')
const occurrenceDate = ref('')
const occurrenceTime = ref('')
const clinicalQuestion = ref('')
const submitOrder = ref(false)
const error = ref('')
const creating = ref(false)

// Watchers for preselected patient
watch(() => props.patient, (p) => {
	if (p) selectedPatient.value = p
})

// The component is always mounted fresh (v-if) when the dialog opens, so
// onMounted is the right hook — it fires after all setup() consts are
// initialized. An immediate watch would run synchronously mid-setup() and
// access fetchOrderForEdit while it is still in the temporal dead zone.
onMounted(() => {
	if (isEditMode.value) {
		// Edit mode: fetch and populate from existing order
		resetForm()
		loadForEdit(props.orderName)
	} else {
		resetForm()
		if (props.patient) {
			selectedPatient.value = props.patient
		}
	}
})

function resetForm() {
	if (!props.patient) {
		selectedPatient.value = ''
		patientSearch.value = ''
	}
	patientOptions.value = []
	templateType.value = ''
	templateSearch.value = ''
	templateOptions.value = []
	selectedTemplate.value = null
	priority.value = 'Routine'
	occurrenceDate.value = ''
	occurrenceTime.value = ''
	clinicalQuestion.value = ''
	submitOrder.value = false
	error.value = ''
	editPatientName.value = ''
}

// Load existing order data for edit mode
const fetchOrderForEdit = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_order_detail',
	method: 'GET',
	onSuccess(response) {
		const raw = response?.raw || {}
		// Patient (read-only in edit mode)
		selectedPatient.value = response.patient || ''
		editPatientName.value = response.patient_name || response.patient || ''
		// Template type
		templateType.value = raw.template_dt || ''
		// Template name — pre-fill search box and mark as selected
		if (raw.template_dn) {
			templateSearch.value = raw.template_dn
			selectedTemplate.value = { name: raw.template_dn }
		}
		// Priority: raw value is the Code Value name (e.g. "Routine-Priority")
		priority.value = raw.priority || 'Routine-Priority'
		// Scheduled date/time
		if (raw.order_date) {
			occurrenceDate.value = raw.order_date.substring(0, 10)
		}
		if (raw.order_time) {
			occurrenceTime.value = raw.order_time.substring(0, 5)
		}
		// Notes
		clinicalQuestion.value = raw.order_description || ''
	},
	onError() {
		error.value = 'Failed to load order details'
	},
})

function loadForEdit(name) {
	if (name) {
		fetchOrderForEdit.fetch({ order_name: name })
	}
}

// Patient search
const patientResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_patients',
	method: 'GET',
	onSuccess(response) {
		// Handle various response shapes from frappe-ui createResource
		if (response && Array.isArray(response.data)) {
			patientOptions.value = response.data
		} else if (response && Array.isArray(response.patients)) {
			patientOptions.value = response.patients
		} else if (Array.isArray(response)) {
			patientOptions.value = response
		} else {
			patientOptions.value = []
		}
	},
})

let patientSearchTimeout = null
function searchPatients() {
	clearTimeout(patientSearchTimeout)
	patientSearchTimeout = setTimeout(() => {
		if (patientSearch.value.length >= 2) {
			patientResource.fetch({ search: patientSearch.value, page_size: 10 })
		} else {
			patientOptions.value = []
		}
	}, 300)
}

function selectPatient(p) {
	selectedPatient.value = p.name
	patientSearch.value = p.patient_name
	patientOptions.value = []
}

// Template search
const templateResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_orderable_templates',
	method: 'GET',
	onSuccess(response) {
		// response may be the array directly, or may have a nested structure
		if (Array.isArray(response)) {
			templateOptions.value = response
		} else if (response && Array.isArray(response.message)) {
			templateOptions.value = response.message
		} else {
			templateOptions.value = []
		}
	},
})

let templateSearchTimeout = null
function searchTemplates() {
	selectedTemplate.value = null
	clearTimeout(templateSearchTimeout)
	templateSearchTimeout = setTimeout(() => {
		if (templateSearch.value.length >= 1 && templateType.value) {
			templateResource.fetch({
				search: templateSearch.value,
				template_type: templateType.value,
			})
		} else {
			templateOptions.value = []
		}
	}, 300)
}

function selectTemplate(t) {
	selectedTemplate.value = t
	templateSearch.value = t.name
	templateOptions.value = []
}

// Create order
const createOrderResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.create_service_request',
	method: 'POST',
	onSuccess(response) {
		creating.value = false
		emit('order-created', response)
		show.value = false
	},
	onError(err) {
		creating.value = false
		error.value = err.messages?.[0] || err.message || 'Failed to create order'
	},
})

// Update existing draft order
const updateOrderResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.update_service_request',
	method: 'POST',
	onSuccess(response) {
		creating.value = false
		emit('order-updated', response)
		show.value = false
	},
	onError(err) {
		creating.value = false
		error.value = err.messages?.[0] || err.message || 'Failed to save order'
	},
})

function createOrder() {
	error.value = ''
	const patient = selectedPatient.value || props.patient
	if (!patient) {
		error.value = 'Please select a patient'
		return
	}
	if (!templateType.value || !selectedTemplate.value) {
		error.value = 'Please select an order type and template'
		return
	}

	creating.value = true
	let occurrence = ''
	if (occurrenceDate.value) {
		occurrence = occurrenceDate.value
		if (occurrenceTime.value) {
			occurrence += ' ' + occurrenceTime.value
		}
	}

	createOrderResource.fetch({
		patient: patient,
		template_dt: templateType.value,
		template_dn: selectedTemplate.value.name,
		priority: priority.value,
		occurrence: occurrence,
		clinical_question: clinicalQuestion.value,
		submit_request: submitOrder.value ? 1 : 0,
	})
}

function saveOrder() {
	error.value = ''
	if (!props.orderName) return

	creating.value = true
	const occurrence = occurrenceDate.value
		? occurrenceDate.value + (occurrenceTime.value ? ' ' + occurrenceTime.value : '')
		: ''

	updateOrderResource.fetch({
		order_name: props.orderName,
		priority: priority.value,
		occurrence: occurrence,
		clinical_question: clinicalQuestion.value,
		template_dt: templateType.value || undefined,
		template_dn: selectedTemplate.value?.name || undefined,
		submit_request: submitOrder.value ? 1 : 0,
	})
}
</script>
