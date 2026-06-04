<template>
	<div>
		<!-- Header with search and register button -->
		<div class="flex items-center justify-between gap-4 p-4">
			<div class="flex-1 max-w-md">
				<FormControl
					v-model="searchQuery"
					type="text"
					placeholder="Search patients by name, MRN, email, mobile..."
					@input="debouncedSearch"
				/>
			</div>
			<Button variant="solid" @click="showRegister = true">
				<template #prefix>
					<FeatherIcon name="user-plus" class="h-4" />
				</template>
				Register Patient
			</Button>
		</div>

		<!-- Patient Grid -->
		<div class="py-2 relative min-h-[75vh] flex flex-col">
			<div
				v-if="patients.length"
				class="flex-1 overflow-y-auto p-2"
			>
				<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
					<Card
						v-for="patient in patients"
						:key="patient.name"
						class="cursor-pointer rounded-xl border border-gray-200 transition-transform
							hover:scale-105 duration-200 hover:drop-shadow-md p-3 bg-white
							min-h-[150px] min-w-[220px] !shadow-none drop-shadow-xl"
						@click="$emit('view-patient', patient)"
					>
						<div class="flex items-center gap-3 mb-2">
							<img
								v-if="patient.image"
								:src="patient.image"
								class="w-10 h-10 rounded-full object-cover border"
							/>
							<div
								v-else
								class="w-10 h-10 rounded-full flex items-center justify-center
									bg-gray-100 text-gray-600 font-bold text-sm border"
							>
								{{ patient.patient_name?.charAt(0)?.toUpperCase() }}
							</div>
							<div class="flex-1 min-w-0">
								<h3 class="text-sm font-semibold text-gray-900 truncate">
									{{ patient.patient_name }}
								</h3>
								<p class="text-xs text-gray-500 truncate">
									{{ patient.uid || patient.name }}
								</p>
							</div>
						</div>

						<div class="space-y-1 text-xs text-gray-600">
							<p v-if="patient.sex">
								<FeatherIcon name="user" class="inline w-3 h-3 mr-1 text-gray-400" />
								{{ patient.sex }}
								<span v-if="patient.dob"> &middot; DOB: {{ formatDate(patient.dob) }}</span>
							</p>
							<p v-if="patient.email" class="truncate">
								<FeatherIcon name="mail" class="inline w-3 h-3 mr-1 text-gray-400" />
								{{ patient.email }}
							</p>
							<p v-if="patient.mobile">
								<FeatherIcon name="phone" class="inline w-3 h-3 mr-1 text-gray-400" />
								{{ patient.mobile }}
							</p>
						</div>
					</Card>
				</div>
			</div>

			<!-- Empty state -->
			<div
				v-else-if="!loading"
				class="flex flex-col items-center justify-center flex-grow text-center p-6"
			>
				<FeatherIcon name="users" class="w-12 h-12 text-gray-400 mb-3" />
				<h2 class="text-lg font-semibold text-gray-700">No Patients Found</h2>
				<p class="text-sm text-gray-500">
					{{ searchQuery ? 'Try a different search term.' : 'Register a new patient to get started.' }}
				</p>
			</div>

			<!-- Loading -->
			<div v-if="loading" class="flex items-center justify-center py-8">
				<div class="text-sm text-gray-500">Loading patients...</div>
			</div>

			<!-- Pagination -->
			<div v-if="totalPages > 1" class="flex justify-center items-center space-x-2 mt-auto pt-4">
				<Button variant="subtle" :disabled="currentPage === 1" @click="goToPage(currentPage - 1)">
					Prev
				</Button>
				<span class="text-sm text-gray-600">
					Page {{ currentPage }} of {{ totalPages }}
				</span>
				<Button variant="subtle" :disabled="currentPage === totalPages" @click="goToPage(currentPage + 1)">
					Next
				</Button>
			</div>
		</div>

		<!-- Register Patient Dialog -->
		<Dialog v-model="showRegister" :options="{ size: '2xl' }">
			<template #body-title>
				<h3 class="text-lg font-semibold">Register New Patient</h3>
			</template>
			<template #body-content>
				<div class="grid grid-cols-2 gap-4">
					<FormControl v-model="registerForm.first_name" label="First Name" type="text" :required="true" />
					<FormControl v-model="registerForm.last_name" label="Last Name" type="text" />
					<FormControl v-model="registerForm.sex" label="Sex" type="select"
						:options="[
							{ label: 'Male', value: 'Male' },
							{ label: 'Female', value: 'Female' },
						]"
					/>
					<FormControl v-model="registerForm.dob" label="Date of Birth" type="date" />
					<FormControl v-model="registerForm.email" label="Email" type="email" />
					<FormControl v-model="registerForm.mobile" label="Mobile" type="text" />
					<FormControl v-model="registerForm.uid" label="MRN / UID" type="text" class="col-span-2" />
				</div>
				<ErrorMessage v-if="registerError" :message="registerError" class="mt-4" />
			</template>
			<template #actions>
				<div class="flex gap-2">
					<Button variant="subtle" @click="showRegister = false">Cancel</Button>
					<Button
						variant="solid"
						:loading="registering"
						:disabled="!registerForm.first_name"
						@click="registerPatient"
					>
						Register
					</Button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { createResource, FormControl, ErrorMessage } from 'frappe-ui'
import { formatDate } from '@/utils/formatters'

const emit = defineEmits(['view-patient'])

const searchQuery = ref('')
const patients = ref([])
const currentPage = ref(1)
const totalPages = ref(1)
const loading = ref(false)

// Register form
const showRegister = ref(false)
const registering = ref(false)
const registerError = ref('')
const registerForm = ref({
	first_name: '',
	last_name: '',
	sex: 'Male',
	dob: '',
	email: '',
	mobile: '',
	uid: '',
})

let searchTimeout = null

function debouncedSearch() {
	clearTimeout(searchTimeout)
	searchTimeout = setTimeout(() => {
		currentPage.value = 1
		fetchPatients()
	}, 300)
}

const fetchPatientsResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_patients',
	method: 'GET',
	onSuccess(response) {
		patients.value = response.patients || []
		totalPages.value = response.total_pages || 1
		loading.value = false
	},
	onError() {
		patients.value = []
		loading.value = false
	},
})

function fetchPatients() {
	loading.value = true
	const params = {
		page: currentPage.value,
		page_size: 20,
	}
	if (searchQuery.value) {
		params.search = searchQuery.value
	}
	fetchPatientsResource.fetch(params)
}

function goToPage(page) {
	currentPage.value = page
	fetchPatients()
}

const registerPatientResource = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.register_patient',
	method: 'POST',
	onSuccess() {
		showRegister.value = false
		registering.value = false
		registerError.value = ''
		registerForm.value = { first_name: '', last_name: '', sex: 'Male', dob: '', email: '', mobile: '', uid: '' }
		fetchPatients()
	},
	onError(error) {
		registering.value = false
		registerError.value = error.messages?.[0] || error.message || 'Failed to register patient'
	},
})

function registerPatient() {
	registering.value = true
	registerError.value = ''
	registerPatientResource.submit(registerForm.value)
}

onMounted(fetchPatients)
</script>
