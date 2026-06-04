import { createApp } from 'vue'
import EventReportsDashboard from './EventReportsDashboard.vue'

import './index.css'

import {
  FrappeUI,
  Button,
  Dialog,
  Badge,
  Tooltip,
  LoadingIndicator,
  Alert,
  setConfig,
  frappeRequest,
  FeatherIcon,
} from 'frappe-ui'

const globalComponents = {
  Button,
  Dialog,
  Badge,
  Tooltip,
  LoadingIndicator,
  Alert,
  FeatherIcon,
}

const app = createApp(EventReportsDashboard)
setConfig('resourceFetcher', frappeRequest)
app.use(FrappeUI)

for (const key in globalComponents) {
  app.component(key, globalComponents[key])
}

app.mount('#app')
