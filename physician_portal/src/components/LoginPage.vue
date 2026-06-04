<template>
	<div class="min-h-screen flex items-center justify-center bg-gray-50">
		<div class="w-full max-w-md">
			<!-- Logo / Title -->
			<div class="text-center mb-8">
				<div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 text-white mb-4">
					<svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M22 12h-4l-3 9L9 3l-3 9H2" />
					</svg>
				</div>
				<h1 class="text-2xl font-bold text-gray-900">Physician Portal</h1>
				<p class="text-sm text-gray-500 mt-1">Sign in to access patient and order management</p>
			</div>

			<!-- Login Card -->
			<div class="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
				<form @submit.prevent="doLogin">
					<div class="space-y-4">
						<!-- Email -->
						<div>
							<label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
							<input
								id="email"
								v-model="email"
								type="text"
								autocomplete="username"
								placeholder="admin@example.com"
								class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
								:disabled="loading"
								ref="emailInput"
							/>
						</div>

						<!-- Password -->
						<div>
							<label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
							<input
								id="password"
								v-model="password"
								type="password"
								autocomplete="current-password"
								placeholder="Password"
								class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
								:disabled="loading"
							/>
						</div>
					</div>

					<!-- Error Message -->
					<div v-if="errorMessage" class="mt-4 p-3 rounded-lg bg-red-50 border border-red-200">
						<p class="text-sm text-red-700">{{ errorMessage }}</p>
					</div>

					<!-- Submit -->
					<Button
						class="w-full mt-6"
						variant="solid"
						size="md"
						:loading="loading"
						@click="doLogin"
					>
						Sign In
					</Button>
				</form>
			</div>

			<!-- Footer -->
			<p class="text-center text-xs text-gray-400 mt-6">
				Access restricted to Administrators, Healthcare Admins, and Physicians.
			</p>
		</div>
	</div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { Button } from 'frappe-ui'

const emit = defineEmits(['login-success'])

const email = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')
const emailInput = ref(null)

onMounted(() => {
	nextTick(() => {
		emailInput.value?.focus()
	})
})

async function doLogin() {
	if (!email.value || !password.value) {
		errorMessage.value = 'Please enter email and password.'
		return
	}

	loading.value = true
	errorMessage.value = ''

	try {
		const res = await fetch('/api/method/login', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'X-Frappe-CSRF-Token': window.csrf_token,
			},
			body: JSON.stringify({
				usr: email.value,
				pwd: password.value,
			}),
		})

		if (!res.ok) {
			const data = await res.json().catch(() => ({}))
			errorMessage.value = data?.message || 'Invalid credentials. Please try again.'
			loading.value = false
			return
		}

		// Login succeeded — get new CSRF token
		const data = await res.json().catch(() => ({}))

		// Fetch updated CSRF token before checking session
		try {
			const csrfRes = await fetch('/api/method/frappe.auth.get_csrf_token', {
				method: 'GET',
			})
			const csrfData = await csrfRes.json()
			if (csrfData?.message) {
				window.csrf_token = csrfData.message
			}
		} catch (e) {
			// Fallback — continue with stored token
		}

		// Verify the user has the right role for this portal
		const sessionRes = await fetch('/api/method/healthcare.healthcare.api.physician_portal.get_session_user', {
			method: 'GET',
			headers: {
				'X-Frappe-CSRF-Token': window.csrf_token,
			},
		})

		if (!sessionRes.ok) {
			errorMessage.value = 'Could not verify session. Please try again.'
			loading.value = false
			return
		}

		const sessionData = await sessionRes.json()
		const user = sessionData?.message

		if (!user || user.user === 'Guest') {
			errorMessage.value = 'Login failed. Please try again.'
			loading.value = false
			return
		}

		if (!user.has_portal_access) {
			errorMessage.value = 'Access denied. You need an Administrator, Healthcare Administrator, or Physician role.'
			// Log back out since they don't have access
			await fetch('/api/method/logout', {
				method: 'POST',
				headers: { 'X-Frappe-CSRF-Token': window.csrf_token },
			})
			loading.value = false
			return
		}

		emit('login-success', user)
	} catch (err) {
		errorMessage.value = 'Network error. Please check your connection and try again.'
		loading.value = false
	}
}
</script>
