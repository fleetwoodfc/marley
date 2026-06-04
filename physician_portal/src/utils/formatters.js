import { createDocumentResource } from "frappe-ui"

const settings = createDocumentResource({
	doctype: "System Settings",
	name: "System Settings",
	auto: false,
})

export const formatDate = (dateStr) => {
	if (!dateStr) return ''
	return new Date(dateStr).toLocaleDateString("en-IN", {
		weekday: "long",
		year: "numeric",
		month: "long",
		day: "numeric",
	})
}

export const formatDateTime = (dateStr) => {
	if (!dateStr) return ''
	return new Date(dateStr).toLocaleString("en-IN", {
		year: "numeric",
		month: "short",
		day: "numeric",
		hour: "2-digit",
		minute: "2-digit",
		hour12: false,
	})
}

export const getStatusColor = (status) => {
	switch (status) {
		case "Completed":
		case "Paid":
		case "Approved":
		case "Confirmed":
		case "Active":
			return "green"
		case "Scheduled":
		case "Open":
		case "In Progress":
		case "Pending":
		case "Partly Paid":
			return "orange"
		case "Draft":
		case "Ordered":
			return "blue"
		case "Cancelled":
		case "Rejected":
		case "Unpaid":
			return "red"
		default:
			return "gray"
	}
}
