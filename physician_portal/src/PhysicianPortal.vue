<template>
	<!-- Auth check loading -->
	<div v-if="authChecking" class="min-h-screen flex items-center justify-center bg-gray-50">
		<div class="text-center">
			<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
			<p class="text-sm text-gray-500 mt-3">Loading...</p>
		</div>
	</div>

	<!-- Login Page -->
	<LoginPage
		v-else-if="!isAuthenticated"
		@login-success="onLoginSuccess"
	/>

	<!-- Main Portal (authenticated) -->
	<div v-else class="w-full h-full">
		<!-- Top bar with user info -->
		<div class="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
			<div class="flex items-center gap-2">
				<div class="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-blue-600 text-white">
					<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M22 12h-4l-3 9L9 3l-3 9H2" />
					</svg>
				</div>
				<span class="text-sm font-semibold text-gray-900">Physician Portal</span>
			</div>
			<div class="flex items-center gap-3">
				<span class="text-xs text-gray-500">{{ sessionUser?.full_name }}</span>
				<Badge v-if="primaryRole" size="sm" variant="subtle" theme="blue">{{ primaryRole }}</Badge>
				<Button variant="ghost" size="sm" @click="doLogout" :loading="loggingOut">
					Sign Out
				</Button>
			</div>
		</div>

		<div>
			<Tabs as="div" v-model="portal_tabs" :tabs="tabs">
				<template #tab-panel="{ tab }">
					<div v-if="tab.label === 'Patients'">
						<PatientList
							@view-patient="viewPatient"
						/>
					</div>
					<div v-else-if="tab.label === 'Orders'">
						<OrderList
							ref="orderListRef"
							:selected-patient="selectedPatientForOrders"
							@view-order="viewOrder"
							@create-order="openCreateOrder"
							@edit-order="editOrder"
						/>
					</div>
					<div v-else-if="tab.label === 'Imaging'">
						<ImagingList />
					</div>
					<div v-else-if="tab.label === 'Reports'">
						<DiagnosticReportList
							ref="reportListRef"
							@view-report="viewReport"
						/>
					</div>
				</template>
			</Tabs>
		</div>
	</div>

	<!-- Patient Detail Dialog -->
	<PatientDetail
		v-if="showPatientDetail"
		v-model="showPatientDetail"
		:patient="selectedPatient"
		@create-order="openCreateOrderForPatient"
	/>

	<!-- Order Detail Dialog -->
	<OrderDetail
		v-if="showOrderDetail"
		v-model="showOrderDetail"
		:order-name="selectedOrder"
		@edit-order="editOrder"
	/>

	<!-- Diagnostic Report Detail Dialog -->
	<DiagnosticReportDetail
		v-if="showReportDetail"
		v-model="showReportDetail"
		:report-name="selectedReport"
		@status-changed="onReportStatusChanged"
	/>

	<!-- Create / Edit Order Dialog -->
	<CreateOrder
		v-if="showCreateOrder"
		v-model="showCreateOrder"
		:patient="preselectedPatient"
		:order-name="editOrderName"
		@order-created="onOrderCreated"
		@order-updated="onOrderUpdated"
	/>

	<!-- Alert Dialog -->
	<Dialog :options="{
		title: dialog_title,
		message: dialog_message,
		size: 'xl',
		icon: {
			name: 'alert-triangle',
			appearance: 'warning',
		},
		actions: [
			{
				label: 'OK',
				variant: 'solid',
			},
		],
	}" v-model="alert_dialog" @click="alert_dialog = false" />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import LoginPage from '@/components/LoginPage.vue'
import PatientList from '@/components/PatientList.vue'
import OrderList from '@/components/OrderList.vue'
import ImagingList from '@/components/ImagingList.vue'
import PatientDetail from '@/components/PatientDetail.vue'
import OrderDetail from '@/components/OrderDetail.vue'
import DiagnosticReportList from '@/components/DiagnosticReportList.vue'
import DiagnosticReportDetail from '@/components/DiagnosticReportDetail.vue'
import CreateOrder from '@/components/CreateOrder.vue'

import {
	createResource,
	Tabs,
	Dialog,
	Badge,
	Button,
} from 'frappe-ui'

// Auth state
const authChecking = ref(true)
const isAuthenticated = ref(false)
const sessionUser = ref(null)
const loggingOut = ref(false)

let alert_dialog = ref(false)
const portal_tabs = ref(0)
let dialog_title = ref('')
let dialog_message = ref('')

// Patient detail state
const showPatientDetail = ref(false)
const selectedPatient = ref(null)

// Order detail state
const showOrderDetail = ref(false)
const selectedOrder = ref(null)

// Report detail state
const showReportDetail = ref(false)
const selectedReport = ref(null)
const reportListRef = ref(null)

// Create order state
const showCreateOrder = ref(false)
const preselectedPatient = ref(null)
const selectedPatientForOrders = ref(null)
const editOrderName = ref(null)
const orderListRef = ref(null)

let healthcareSettings = ref({})

const primaryRole = computed(() => {
	if (!sessionUser.value?.roles) return null
	// Show most specific role
	const priority = ['Physician', 'Healthcare Administrator', 'Administrator', 'System Manager']
	for (const r of priority) {
		if (sessionUser.value.roles.includes(r)) return r
	}
	return sessionUser.value.roles[0] || null
})

// Check session on mount
onMounted(async () => {
	await checkSession()
})

async function checkSession() {
	authChecking.value = true
	try {
		const res = await fetch('/api/method/healthcare.healthcare.api.physician_portal.get_session_user', {
			method: 'GET',
			headers: {
				'X-Frappe-CSRF-Token': window.csrf_token,
			},
		})
		if (res.ok) {
			const data = await res.json()
			const user = data?.message
			if (user && user.user !== 'Guest' && user.has_portal_access) {
				sessionUser.value = user
				isAuthenticated.value = true
				loadPortalData()
			}
		}
	} catch (e) {
		// Session check failed — show login
	}
	authChecking.value = false
}

function onLoginSuccess(user) {
	sessionUser.value = user
	isAuthenticated.value = true
	loadPortalData()
}

async function doLogout() {
	loggingOut.value = true
	try {
		await fetch('/api/method/logout', {
			method: 'POST',
			headers: {
				'X-Frappe-CSRF-Token': window.csrf_token,
			},
		})
	} catch (e) {
		// Ignore errors
	}
	// Reset state
	isAuthenticated.value = false
	sessionUser.value = null
	loggingOut.value = false
	// Fetch new CSRF token for guest session
	try {
		const csrfRes = await fetch('/api/method/frappe.auth.get_csrf_token')
		const csrfData = await csrfRes.json()
		if (csrfData?.message) {
			window.csrf_token = csrfData.message
		}
	} catch (e) {
		// Fallback
	}
}

function loadPortalData() {
	getHealthcareSettings.fetch()
	getPractitioner.fetch()
}

let getHealthcareSettings = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_settings',
	method: 'GET',
	onSuccess(response) {
		if (response) {
			healthcareSettings.value = response
		}
	},
})

let getPractitioner = createResource({
	url: '/api/method/healthcare.healthcare.api.physician_portal.get_logged_in_practitioner',
	method: 'GET',
})

const tabs = computed(() => {
	return [
		{ label: 'Patients' },
		{ label: 'Orders' },
		{ label: 'Imaging' },
		{ label: 'Reports' },
	]
})

function viewPatient(patient) {
	selectedPatient.value = patient
	showPatientDetail.value = true
}

function viewOrder(order) {
	selectedOrder.value = typeof order === 'string' ? order : order?.name
	showOrderDetail.value = true
}

function viewReport(report) {
	selectedReport.value = typeof report === 'string' ? report : report?.name
	showReportDetail.value = true
}

function onReportStatusChanged() {
	// Refresh the reports list after a status change
	if (reportListRef.value?.refresh) {
		reportListRef.value.refresh()
	}
}

function openCreateOrder() {
	preselectedPatient.value = null
	editOrderName.value = null
	showCreateOrder.value = true
}

function openCreateOrderForPatient(patientName) {
	preselectedPatient.value = patientName
	editOrderName.value = null
	showCreateOrder.value = true
}

function editOrder(order) {
	// order can be an object or a string (order name)
	const name = typeof order === 'string' ? order : order?.name
	preselectedPatient.value = null
	editOrderName.value = name
	showCreateOrder.value = true
}

function onOrderCreated() {
	showCreateOrder.value = false
	editOrderName.value = null
	// Switch to Orders tab
	portal_tabs.value = 1
	orderListRef.value?.refresh()
}

function onOrderUpdated() {
	showCreateOrder.value = false
	editOrderName.value = null
	// Refresh the orders list
	portal_tabs.value = 1
	orderListRef.value?.refresh()
}
</script>
