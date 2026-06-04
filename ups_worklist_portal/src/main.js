import { createApp } from 'vue'
import WorklistDashboard from './WorklistDashboard.vue'
import { initSocket } from './socket'

import './index.css'

import {
  FrappeUI,
  Button,
  Dialog,
  Badge,
  Tooltip,
  setConfig,
  frappeRequest,
  FeatherIcon,
  Card,
} from 'frappe-ui'

const globalComponents = {
  Button,
  Dialog,
  Badge,
  Tooltip,
  FeatherIcon,
  Card,
}

const app = createApp(WorklistDashboard)
setConfig('resourceFetcher', frappeRequest)
app.use(FrappeUI)
app.provide('$socket', initSocket())

for (const key in globalComponents) {
  app.component(key, globalComponents[key])
}

app.mount('#app')
