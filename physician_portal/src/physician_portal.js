import { createApp } from 'vue'
import PhysicianPortal from './PhysicianPortal.vue'
import { initSocket } from './socket'

import './index.css'

import {
	FrappeUI,
	Button,
	Dialog,
	Badge,
	setConfig,
	frappeRequest,
	FeatherIcon,
	Tooltip,
	Card
} from 'frappe-ui'

let globalComponents = {
	Button,
	Dialog,
	Badge,
	FeatherIcon,
	Tooltip,
	Card
}

let app = createApp(PhysicianPortal)
setConfig('resourceFetcher', frappeRequest)
app.use(FrappeUI)
app.provide('$socket', initSocket())

for (let key in globalComponents) {
	app.component(key, globalComponents[key])
}

app.mount('#app')
