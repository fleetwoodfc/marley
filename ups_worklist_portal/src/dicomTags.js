/**
 * DICOM+JSON tag utilities for UPS N-EVENT-REPORT parsing.
 *
 * Tag definitions follow DICOM Supplement 96 Table UUU.2.4-1
 * "Report a Change in UPS Status – EVENT REPORT INFORMATION".
 *
 * DICOM+JSON format (PS3.18 §F.2.2):
 *   { "<tag>": { "vr": "<VR>", "Value": [...] }, ... }
 * where <tag> is an 8-character uppercase hex string without commas.
 */

// ── Tag constants ──────────────────────────────────────────────────────────
export const TAGS = {
  // Sup-96 Table UUU.2.4-1 – Event Type 1: UPS State Report
  PROCEDURE_STEP_STATE:    '00741000',
  INPUT_READINESS_STATE:   '00404041',
  REASON_FOR_CANCELLATION: '00741238',
  DISCONTINUATION_REASON_SEQ: '0074100E',

  // Event Type 2: UPS Cancel Requested
  REQUESTING_AE:           '00741236',
  CONTACT_URI:             '0074100A',
  CONTACT_DISPLAY_NAME:    '0074100C',

  // Event Type 3: UPS Progress Report
  PROGRESS_INFORMATION_SEQ:  '00741002',
  PROCEDURE_STEP_PROGRESS:   '00741004',
  PROCEDURE_STEP_PROGRESS_DESC: '00741006',
  COMMS_URI_SEQ:             '00741008',

  // Event Type 4: SCP Status Change
  SCP_STATUS:              '00741242',
  SUBSCRIPTION_LIST_STATUS:'00741244',
  UPS_LIST_STATUS:         '00741246',

  // Code Sequence children
  CODE_VALUE:              '00080100',
  CODING_SCHEME_DESIGNATOR:'00080102',
  CODE_MEANING:            '00080104',
}

// ── Low-level DICOM+JSON helpers ───────────────────────────────────────────

/**
 * Parse a raw_request string into a DICOM dataset object.
 * Returns null if parsing fails.
 */
export function parseDicomJson(raw) {
  if (!raw) return null
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    // Normalise tag keys to uppercase for consistent lookup
    const out = {}
    for (const [k, v] of Object.entries(parsed)) {
      out[k.toUpperCase()] = v
    }
    return out
  } catch {
    return null
  }
}

/**
 * Extract scalar string value for a tag.
 * Returns '' if absent or empty.
 */
export function tagValue(dataset, tag) {
  if (!dataset) return ''
  const entry = dataset[tag.toUpperCase()]
  if (!entry) return ''
  const values = entry.Value
  if (!Array.isArray(values) || values.length === 0) return ''
  const first = values[0]
  if (typeof first === 'string') return first
  // PN value
  if (typeof first === 'object' && first !== null) {
    return first.Alphabetic || first.Ideographic || first.Phonetic || ''
  }
  return String(first)
}

/**
 * Extract a sequence (array of datasets) for a tag.
 * Returns [] if absent.
 */
export function tagSeq(dataset, tag) {
  if (!dataset) return []
  const entry = dataset[tag.toUpperCase()]
  if (!entry || !Array.isArray(entry.Value)) return []
  return entry.Value
}

/**
 * Format a code sequence item as "Meaning (Value, Scheme)".
 */
export function formatCode(item) {
  if (!item) return ''
  const meaning = tagValue(item, TAGS.CODE_MEANING)
  const value   = tagValue(item, TAGS.CODE_VALUE)
  const scheme  = tagValue(item, TAGS.CODING_SCHEME_DESIGNATOR)
  if (!meaning && !value) return ''
  if (value && scheme) return `${meaning} (${value}, ${scheme})`
  if (value) return `${meaning} (${value})`
  return meaning
}

// ── Sup-96 Table UUU.2.4-1 extraction ─────────────────────────────────────

/**
 * Extract structured Event Report Information from a DICOM+JSON dataset
 * according to event type.
 *
 * Returns an object with the following optional keys:
 *   eventTypeId      – 1 | 2 | 3 | 4 (DICOM N-EVENT-REPORT Event Type ID)
 *   procedureStepState
 *   inputReadinessState
 *   reasonForCancellation
 *   discontinuationReasonCodes   – array of { value, scheme, meaning }
 *   requestingAe
 *   contactUri
 *   contactDisplayName
 *   stepProgress                 – 0-100 or null
 *   stepProgressDesc
 *   commsContacts                – array of { uri, name }
 *   scpStatus
 *   subscriptionListStatus
 *   upsList Status
 */
export function extractEventReportInfo(raw, eventType) {
  const ds = parseDicomJson(raw)
  if (!ds) return null

  const info = {}

  // ── Event Type 1: UPS State Report ──────────────────────────────────────
  if (['CREATE', 'CLAIM', 'COMPLETE', 'CANCEL', 'UPDATE', 'REASSIGN'].includes(eventType)) {
    info.eventTypeId = 1

    const state = tagValue(ds, TAGS.PROCEDURE_STEP_STATE)
    if (state) info.procedureStepState = state

    const readiness = tagValue(ds, TAGS.INPUT_READINESS_STATE)
    if (readiness) info.inputReadinessState = readiness

    const reason = tagValue(ds, TAGS.REASON_FOR_CANCELLATION)
    if (reason) info.reasonForCancellation = reason

    const discSeq = tagSeq(ds, TAGS.DISCONTINUATION_REASON_SEQ)
    if (discSeq.length) {
      info.discontinuationReasonCodes = discSeq.map((item) => {
        const child = {}
        for (const [k, v] of Object.entries(item)) child[k.toUpperCase()] = v
        return {
          value:   tagValue(child, TAGS.CODE_VALUE),
          scheme:  tagValue(child, TAGS.CODING_SCHEME_DESIGNATOR),
          meaning: tagValue(child, TAGS.CODE_MEANING),
          formatted: formatCode(child),
        }
      })
    }
  }

  // ── Event Type 2: UPS Cancel Requested ──────────────────────────────────
  if (eventType === 'CANCEL_REQUEST') {
    info.eventTypeId = 2

    const reqAe = tagValue(ds, TAGS.REQUESTING_AE)
    if (reqAe) info.requestingAe = reqAe

    const reason = tagValue(ds, TAGS.REASON_FOR_CANCELLATION)
    if (reason) info.reasonForCancellation = reason

    const discSeq = tagSeq(ds, TAGS.DISCONTINUATION_REASON_SEQ)
    if (discSeq.length) {
      info.discontinuationReasonCodes = discSeq.map((item) => {
        const child = {}
        for (const [k, v] of Object.entries(item)) child[k.toUpperCase()] = v
        return {
          value:   tagValue(child, TAGS.CODE_VALUE),
          scheme:  tagValue(child, TAGS.CODING_SCHEME_DESIGNATOR),
          meaning: tagValue(child, TAGS.CODE_MEANING),
          formatted: formatCode(child),
        }
      })
    }

    const contactUri = tagValue(ds, TAGS.CONTACT_URI)
    if (contactUri) info.contactUri = contactUri

    const contactName = tagValue(ds, TAGS.CONTACT_DISPLAY_NAME)
    if (contactName) info.contactDisplayName = contactName
  }

  // ── Event Type 3: UPS Progress Report ───────────────────────────────────
  // UPDATE events may carry a progress information sequence
  if (eventType === 'UPDATE') {
    const progSeq = tagSeq(ds, TAGS.PROGRESS_INFORMATION_SEQ)
    if (progSeq.length) {
      info.eventTypeId = 3
      const first = {}
      for (const [k, v] of Object.entries(progSeq[0])) first[k.toUpperCase()] = v

      const pct = tagValue(first, TAGS.PROCEDURE_STEP_PROGRESS)
      if (pct !== '') info.stepProgress = parseFloat(pct)

      const desc = tagValue(first, TAGS.PROCEDURE_STEP_PROGRESS_DESC)
      if (desc) info.stepProgressDesc = desc

      const commsSeq = tagSeq(first, TAGS.COMMS_URI_SEQ)
      if (commsSeq.length) {
        info.commsContacts = commsSeq.map((c) => {
          const cc = {}
          for (const [k, v] of Object.entries(c)) cc[k.toUpperCase()] = v
          return {
            uri:  tagValue(cc, TAGS.CONTACT_URI),
            name: tagValue(cc, TAGS.CONTACT_DISPLAY_NAME),
          }
        })
      }
    }
  }

  // ── Event Type 4: SCP Status Change ─────────────────────────────────────
  if (eventType === 'RECONCILE') {
    const scpStatus = tagValue(ds, TAGS.SCP_STATUS)
    if (scpStatus) {
      info.eventTypeId   = 4
      info.scpStatus     = scpStatus
    }

    const subStatus = tagValue(ds, TAGS.SUBSCRIPTION_LIST_STATUS)
    if (subStatus) info.subscriptionListStatus = subStatus

    const upsStatus = tagValue(ds, TAGS.UPS_LIST_STATUS)
    if (upsStatus) info.upsListStatus = upsStatus
  }

  // Return null if nothing was extracted (e.g. raw_request was not an N-EVENT-REPORT)
  const hasData = Object.keys(info).some((k) => k !== 'eventTypeId')
  return hasData ? info : null
}

// ── Display helpers ────────────────────────────────────────────────────────

export const EVENT_TYPE_ID_LABELS = {
  1: 'UPS State Report (Type 1)',
  2: 'UPS Cancel Requested (Type 2)',
  3: 'UPS Progress Report (Type 3)',
  4: 'SCP Status Change (Type 4)',
}
