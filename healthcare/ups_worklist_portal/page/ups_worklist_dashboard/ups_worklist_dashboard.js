/**
 * UPS Dashboard — Frappe Page
 *
 * IHE Radiology Remote Reading Workflow (RRR-WF) §40.4.2 Use Cases:
 *   UC1 — Open Worklist:       SCHEDULED, no assigned performer (community pool)
 *   UC2 — Assigned Read:       SCHEDULED, assigned to a specific scheduled performer
 *   UC3 — Report Addendum:     COMPLETED (recent) + create-addendum action
 *   UC4 — Re-assignment:       Supervisor re-assigns an existing assignment
 *   UC5 — Cancellation:        Cancel request advisory + cancel-requested pending items
 *   UC6 — Failure:             Performer self-cancels a claimed workitem
 *
 * Additional tabs:
 *   In Progress — all currently claimed items (UC5/UC6 actions)
 *   All         — unified filterable view (original behaviour, T024-T036)
 *
 * Pre-existing task coverage:
 *   T024 — filterable worklist, claim/complete actions, realtime refresh
 *   T025 — 409 conflict UX (optimistic rollback + row refresh)
 *   T029 — supervisor cancel/reassign panel
 *   T030 — orphaned workitem highlighting + reschedule
 *   T035 — audit event history tab
 *   T036 — reconciliation panel
 */

// -------------------------------------------------------------------------
// Constants
// -------------------------------------------------------------------------
const API = "ups_worklist_portal.api.ups_actions";
const UPS_STATES = ["SCHEDULED", "IN PROGRESS", "COMPLETED", "CANCELED"];
const STATE_BADGE = {
  SCHEDULED: "blue",
  "IN PROGRESS": "orange",
  COMPLETED: "green",
  CANCELED: "gray",
};

/**
 * IHE RRR-WF §40.4.2 use-case tab definitions.
 * id must match the worklist_type expected by get_worklist_by_type() on the server,
 * except for "all" which maps to the legacy get_worklist() endpoint.
 */
const WORKLIST_TABS = [
  {
    id: "open",
    label: __("Open Worklist"),
    title: __(
      "UC1 — SCHEDULED workitems available for any qualified Task Performer to claim (community pool)"
    ),
    badge_class: "badge-primary",
  },
  {
    id: "assigned",
    label: __("Assigned"),
    title: __(
      "UC2 / UC4 — SCHEDULED workitems assigned to a specific Task Performer; supervisor may re-assign"
    ),
    badge_class: "badge-info",
  },
  {
    id: "in_progress",
    label: __("In Progress"),
    title: __(
      "UC5 / UC6 — All IN PROGRESS (claimed) workitems; perform completion, cancel-request, or failure self-cancel"
    ),
    badge_class: "badge-warning",
  },
  {
    id: "cancel_requested",
    label: __("Cancel Requested"),
    title: __(
      "UC5 — IN PROGRESS workitems with a pending cancel request awaiting performer action"
    ),
    badge_class: "badge-danger",
  },
  {
    id: "addendum",
    label: __("Addendum"),
    title: __(
      "UC3 — Recently COMPLETED workitems; create an addendum workitem for a follow-up read"
    ),
    badge_class: "badge-success",
  },
  {
    id: "all",
    label: __("All Workitems"),
    title: __("Unified filterable view across all states"),
    badge_class: "badge-secondary",
  },
];

// -------------------------------------------------------------------------
// Page setup
// -------------------------------------------------------------------------
frappe.pages["ups-worklist-dashboard"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("UPS Dashboard"),
    single_column: true,
  });

  ups_worklist_dashboard.init(page, wrapper);
};

frappe.pages["ups-worklist-dashboard"].on_page_hide = function (wrapper) {
  // Prevent listener leak on page exit
  frappe.realtime.off("ups_state_change");
};

// -------------------------------------------------------------------------
// Module
// -------------------------------------------------------------------------
const ups_worklist_dashboard = {
  // State
  _filters: {},
  _ae_mappings: [],
  _current_user_roles: [],
  _selected_uid: null,
  _worklist_data: [],
  _orphaned_uids: new Set(),
  _page: null,
  _active_tab: "open", // IHE RRR-WF use-case tab id

  // -----------------------------------------------------------------------
  init(page, wrapper) {
    this._page = page;
    this._wrapper = wrapper;

    // User roles are reliably available from frappe.boot
    this._current_user_roles =
      (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];

    this._build_layout(wrapper);
    this._bind_realtime();
    this._load_summary();
    this._load_worklist();

    // Fetch AE Mappings from the server (get_context is not called for desk
    // pages, so we load them explicitly and refresh the AET filter dropdown).
    frappe.call({
      method: `${API}.get_ae_mappings`,
      callback: (r) => {
        this._ae_mappings = (r && r.message) ? r.message : [];
        // Refresh the AET filter options now that data is available
        const $aet = $("#ups-filter-aet");
        if ($aet.length) {
          const extra = this._ae_mappings
            .map((m) => `<option value="${m.ae_title}">${m.display_name || m.ae_title}</option>`)
            .join("");
          $aet.find("option:not([value=''])").remove();
          $aet.append(extra);
        }
      },
    });
  },

  // -----------------------------------------------------------------------
  // Layout
  // -----------------------------------------------------------------------
  _build_layout(wrapper) {
    const $main = $(this._page.main);
    $main.empty();

    $main.append(`
      <div class="ups-dashboard-container">
        <!-- Summary bar -->
        <div class="ups-summary-bar" id="ups-summary-bar" style="margin-bottom:1rem;"></div>

        <!-- IHE §40.4.2 use-case tab bar -->
        <div id="ups-tab-bar" style="margin-bottom:0.75rem;"></div>

        <!-- Active tab contextual description -->
        <div id="ups-tab-description" class="alert alert-light py-1 mb-2"
             style="font-size:0.85rem; display:none;"></div>

        <!-- "All" tab filter bar — only shown when the All tab is active -->
        <div class="ups-filter-bar" id="ups-filter-bar" style="margin-bottom:1rem; display:none;">
          <div class="row mx-0">
            <div class="col-sm-2">
              <select id="ups-filter-status" class="form-control form-control-sm" multiple>
                ${UPS_STATES.map(
                  (s) =>
                    `<option value="${s}" ${
                      s === "SCHEDULED" || s === "IN PROGRESS" ? "selected" : ""
                    }>${s}</option>`
                ).join("")}
              </select>
              <small class="text-muted">${__("Status (multi-select)")}</small>
            </div>
            <div class="col-sm-2">
              <select id="ups-filter-aet" class="form-control form-control-sm">
                <option value="">${__("All AE Titles")}</option>
                ${this._ae_mappings
                  .map(
                    (m) =>
                      `<option value="${m.ae_title}">${m.display_name || m.ae_title}</option>`
                  )
                  .join("")}
              </select>
            </div>
            <div class="col-sm-2">
              <input id="ups-filter-modality" type="text" class="form-control form-control-sm"
                     placeholder="${__("Modality")}">
            </div>
            <div class="col-sm-2">
              <input id="ups-filter-patient" type="text" class="form-control form-control-sm"
                     placeholder="${__("Patient Name")}">
            </div>
            <div class="col-sm-2">
              <input id="ups-filter-from" type="datetime-local" class="form-control form-control-sm">
            </div>
            <div class="col-sm-2">
              <button id="ups-btn-filter" class="btn btn-primary btn-sm w-100">${__("Apply Filters")}</button>
              ${
                this._isSupervisorOrEngineer()
                  ? `<button id="ups-btn-reconcile" class="btn btn-default btn-sm w-100 mt-1">${__("Reconciliation\u2026")}</button>`
                  : ""
              }
            </div>
          </div>
        </div>

        <!-- Main split: worklist + detail panel -->
        <div class="row mx-0" id="ups-split-row">
          <div class="col-12" id="ups-table-col">
            <div id="ups-worklist-table"></div>
            <div id="ups-worklist-pager" style="margin-top:0.5rem;"></div>
          </div>
          <div class="col-sm-4" id="ups-detail-col" style="display:none;">
            <div id="ups-detail-panel"></div>
          </div>
        </div>

        <!-- Reconciliation panel placeholder -->
        <div id="ups-reconciliation-container" style="display:none; margin-top:1rem;"></div>
      </div>
    `);

    this._render_tab_bar();
    this._bind_filter_events();
  },

  // -----------------------------------------------------------------------
  // Tab bar — IHE §40.4.2 use-case navigation
  // -----------------------------------------------------------------------
  _render_tab_bar() {
    const self = this;

    // All tabs are shown to Technologist+; Cancel Requested / Addendum visible to all
    const visibleTabs = WORKLIST_TABS;

    const $bar = $("#ups-tab-bar");
    $bar.html(`
      <ul class="nav nav-tabs" id="ups-use-case-tabs" role="tablist">
        ${visibleTabs
          .map(
            (t) => `
          <li class="nav-item" role="presentation">
            <a class="nav-link${t.id === self._active_tab ? " active" : ""}"
               href="#"
               data-tab-id="${t.id}"
               title="${t.title}"
               role="tab">
              ${t.label}
              <span class="ups-tab-count badge ${t.badge_class}"
                    id="ups-tab-count-${t.id}"
                    style="margin-left:4px; font-size:0.7em;"></span>
            </a>
          </li>
        `
          )
          .join("")}
      </ul>
    `);

    $bar.on("click.tabs", "a.nav-link", function (e) {
      e.preventDefault();
      const tabId = $(this).data("tab-id");
      self._switch_tab(tabId);
    });

    this._update_tab_description();
  },

  _switch_tab(tabId) {
    this._active_tab = tabId;
    this._filters = {}; // reset pagination on tab switch

    // Toggle "All" filter bar visibility
    $("#ups-filter-bar").toggle(tabId === "all");

    // Update active tab decoration
    $("#ups-use-case-tabs .nav-link").removeClass("active");
    $(`#ups-use-case-tabs [data-tab-id="${tabId}"]`).addClass("active");

    this._update_tab_description();
    this._load_worklist();
  },

  _update_tab_description() {
    const tab = WORKLIST_TABS.find((t) => t.id === this._active_tab);
    const $desc = $("#ups-tab-description");
    if (tab) {
      $desc.show().text(tab.title);
    } else {
      $desc.hide();
    }
  },

  // -----------------------------------------------------------------------
  // Filter events (only relevant in the "all" tab)
  // -----------------------------------------------------------------------
  _bind_filter_events() {
    const self = this;

    $("#ups-btn-filter").on("click", () => {
      self._collect_filters();
      self._load_worklist();
    });

    $("#ups-filter-modality,#ups-filter-patient").on("keydown", (e) => {
      if (e.key === "Enter") $("#ups-btn-filter").trigger("click");
    });

    $("#ups-btn-reconcile").on("click", () => self._show_reconciliation());
  },

  _collect_filters() {
    const statusEl = document.getElementById("ups-filter-status");
    const status = statusEl
      ? Array.from(statusEl.selectedOptions).map((o) => o.value)
      : ["SCHEDULED", "IN PROGRESS"];

    this._filters = {
      status: JSON.stringify(status),
      ae_title: $("#ups-filter-aet").val() || "",
      modality: $("#ups-filter-modality").val() || "",
      patient_name: $("#ups-filter-patient").val() || "",
      from_datetime: $("#ups-filter-from").val() || "",
      limit: 50,
      offset: this._filters.offset || 0,
    };
  },

  // -----------------------------------------------------------------------
  // Summary bar
  // -----------------------------------------------------------------------
  _load_summary() {
    frappe.call({
      method: `${API}.get_dashboard_summary`,
      error: (r) => {
        console.error("UPS get_dashboard_summary failed:", r);
      },
      callback: (r) => {
        if (!r.message) return;
        const s = r.message;
        this._orphaned_uids = new Set();
        const $bar = $("#ups-summary-bar");
        $bar.html(`
          <div class="ups-summary-badges">
            <span class="badge badge-info">${__("Scheduled")}: ${s.SCHEDULED || 0}</span>
            <span class="badge badge-warning">${__("In Progress")}: ${s.IN_PROGRESS || 0}</span>
            <span class="badge badge-success">${__("Completed")}: ${s.COMPLETED || 0}</span>
            <span class="badge badge-secondary">${__("Canceled")}: ${s.CANCELED || 0}</span>
            ${s.SYNC_ERROR > 0 ? `<span class="badge badge-danger">${__("Sync Errors")}: ${s.SYNC_ERROR}</span>` : ""}
            ${s.ORPHANED > 0 ? `<span class="badge badge-dark ups-orphan-badge">${__("Orphaned")}: ${s.ORPHANED}</span>` : ""}
          </div>
        `);
      },
    });
  },

  // -----------------------------------------------------------------------
  // Worklist load — routes to the correct API method for the active tab
  // -----------------------------------------------------------------------
  _load_worklist() {
    const self = this;

    if (this._active_tab === "all") {
      // Legacy unified worklist (T024)
      if (!this._filters.status) this._collect_filters();

      frappe.call({
        method: `${API}.get_worklist`,
        args: this._filters,
        error: (r) => {
          console.error("UPS get_worklist failed:", r);
          frappe.msgprint({
            title: __("Worklist Error"),
            indicator: "red",
            message: __("Failed to load worklist. Check browser console for details."),
          });
        },
        callback: (r) => {
          if (!r.message) return;
          self._worklist_data = r.message.items || [];
          self._render_worklist(r.message.total);
        },
      });
    } else {
      // IHE §40.4.2 use-case specific worklists
      frappe.call({
        method: `${API}.get_worklist_by_type`,
        args: { worklist_type: this._active_tab, limit: 50, offset: 0 },
        error: (r) => {
          console.error("UPS get_worklist_by_type failed:", r);
          frappe.msgprint({
            title: __("Worklist Error"),
            indicator: "red",
            message: __("Failed to load worklist. Check browser console for details."),
          });
        },
        callback: (r) => {
          if (!r.message) return;
          self._worklist_data = r.message.items || [];
          // Update tab badge count
          const countBadge = document.getElementById(`ups-tab-count-${self._active_tab}`);
          if (countBadge) countBadge.textContent = r.message.total || 0;
          self._render_worklist(r.message.total);
        },
      });
    }
  },

  // -----------------------------------------------------------------------
  // Render worklist table — tab-aware columns and action buttons
  // -----------------------------------------------------------------------
  _render_worklist(total) {
    const self = this;
    const $table = $("#ups-worklist-table");

    if (!this._worklist_data.length) {
      $table.html(`<p class="text-muted mt-2">${__("No workitems found.")}</p>`);
      return;
    }

    const isSupOrEng = this._isSupervisorOrEngineer();
    const isSup = this._isSupervisor();
    const isTech = this._isTechnologist();
    const tab = this._active_tab;

    const rows = this._worklist_data
      .map((item) => {
        const badgeColor = STATE_BADGE[item.ups_state] || "gray";
        const isCancelReq = !!item.cancel_requested_at;
        const rowClass = `ups-row${isCancelReq ? " ups-row-cancel-requested" : ""}`;

        const actions = this._build_row_actions(item, tab, isTech, isSup, isSupOrEng);
        // Always append audit-log button for privileged users
        if (isSupOrEng) {
          actions.push(
            `<button class="btn btn-xs btn-link ups-btn-history" data-uid="${item.name}">${__("Log")}</button>`
          );
        }

        const cells = this._build_row_cells(item, tab);

        return `
          <tr class="${rowClass}" data-uid="${item.name}">
            ${cells}
            <td style="white-space:nowrap;">${actions.join("") || "&#8212;"}</td>
          </tr>
        `;
      })
      .join("");

    const headers = this._build_table_headers(tab);

    $table.html(`
      <div style="overflow-x:auto;">
        <table class="table table-sm table-bordered table-hover" style="min-width:700px;">
          <thead class="thead-light">
            <tr>
              ${headers}
              <th>${__("Actions")}</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <small class="text-muted">${__("Total: {0}", [total])}</small>
    `);

    this._bind_action_buttons($table);

    if (isSup) {
      this._bind_legacy_supervisor_buttons();
    }
  },

  // -----------------------------------------------------------------------
  // Build action buttons for a row — returns array of HTML button strings
  // -----------------------------------------------------------------------
  _build_row_actions(item, tab, isTech, isSup, isSupOrEng) {
    const uid = item.name;
    const actions = [];

    if (tab === "open") {
      // UC1 — community pool: any qualified performer may claim
      if (item.ups_state === "SCHEDULED" && isTech) {
        actions.push(
          `<button class="btn btn-xs btn-primary ups-btn-claim" data-uid="${uid}">${__("Claim")}</button>`
        );
      }
      if (isSup) {
        actions.push(
          `<button class="btn btn-xs btn-default ups-btn-assign ml-1" data-uid="${uid}"
               title="${__("Assign to a specific performer (UC2)")}">${__("Assign")}</button>`
        );
        actions.push(
          `<button class="btn btn-xs btn-danger ups-btn-request-cancel ml-1"
               data-uid="${uid}">${__("Cancel")}</button>`
        );
      }

    } else if (tab === "assigned") {
      // UC2/UC4 — assigned performer claims; supervisor may re-assign
      if (item.ups_state === "SCHEDULED" && isTech) {
        actions.push(
          `<button class="btn btn-xs btn-primary ups-btn-claim" data-uid="${uid}">${__("Claim")}</button>`
        );
      }
      if (isSup) {
        actions.push(
          `<button class="btn btn-xs btn-default ups-btn-assign ml-1" data-uid="${uid}"
               title="${__("Re-assign to a different performer (UC4)")}">${__("Re-assign")}</button>`
        );
        actions.push(
          `<button class="btn btn-xs btn-danger ups-btn-request-cancel ml-1"
               data-uid="${uid}">${__("Cancel")}</button>`
        );
      }

    } else if (tab === "in_progress") {
      // UC5/UC6 — complete, request-cancel advisory, or self-cancel (failure)
      const isMine = item.claimed_by === frappe.session.user;
      if (isMine || isSup) {
        actions.push(
          `<button class="btn btn-xs btn-success ups-btn-complete ml-1"
               data-uid="${uid}">${__("Complete")}</button>`
        );
        actions.push(
          `<button class="btn btn-xs btn-warning ups-btn-performer-cancel ml-1"
               data-uid="${uid}"
               title="${__("Cancel due to local failure — performer self-cancel (UC6)")}">${__("Cancel (Failure)")}</button>`
        );
      }
      if (isTech || isSup) {
        actions.push(
          `<button class="btn btn-xs btn-danger ups-btn-request-cancel ml-1"
               data-uid="${uid}"
               title="${__("Send cancel-request advisory to performer (UC5)")}">${__("Request Cancel")}</button>`
        );
      }
      if (isSup) {
        actions.push(
          `<button class="btn btn-xs btn-default ups-btn-reschedule ml-1"
               data-uid="${uid}">${__("Reschedule")}</button>`
        );
      }

    } else if (tab === "cancel_requested") {
      // UC5 — performer decides: honor cancel request or complete anyway
      const isMine = item.claimed_by === frappe.session.user;
      if (isMine || isSup) {
        actions.push(
          `<button class="btn btn-xs btn-warning ups-btn-performer-cancel ml-1"
               data-uid="${uid}"
               title="${__("Honor the cancel request (UC5)")}">${__("Cancel")}</button>`
        );
        actions.push(
          `<button class="btn btn-xs btn-success ups-btn-complete ml-1"
               data-uid="${uid}">${__("Complete Anyway")}</button>`
        );
      }

    } else if (tab === "addendum") {
      // UC3 — create a new addendum workitem from completed original
      if (isTech || isSup) {
        actions.push(
          `<button class="btn btn-xs btn-info ups-btn-addendum ml-1"
               data-uid="${uid}"
               title="${__("Create an addendum workitem for a follow-up read (UC3)")}">${__("Create Addendum")}</button>`
        );
      }

    } else {
      // "all" tab — original combined action set
      const claimable = item.ups_state === "SCHEDULED" && isTech;
      const completeable =
        item.ups_state === "IN PROGRESS" &&
        (item.claimed_by === frappe.session.user || isSup);

      if (claimable) {
        actions.push(
          `<button class="btn btn-xs btn-primary ups-btn-claim" data-uid="${uid}">${__("Claim")}</button>`
        );
      }
      if (completeable) {
        actions.push(
          `<button class="btn btn-xs btn-success ups-btn-complete ml-1"
               data-uid="${uid}">${__("Complete")}</button>`
        );
      }
      if (isSup && (item.ups_state === "SCHEDULED" || item.ups_state === "IN PROGRESS")) {
        actions.push(
          `<button class="btn btn-xs btn-danger ups-btn-cancel ml-1"
               data-uid="${uid}">${__("Cancel")}</button>`
        );
      }
      if (isSup && item.ups_state === "SCHEDULED") {
        actions.push(
          `<button class="btn btn-xs btn-default ups-btn-reassign ml-1"
               data-uid="${uid}">${__("Reassign AET")}</button>`
        );
      }
      if (item.ups_state === "COMPLETED" && isTech) {
        actions.push(
          `<button class="btn btn-xs btn-info ups-btn-addendum ml-1"
               data-uid="${uid}">${__("Addendum")}</button>`
        );
      }
    }

    return actions;
  },

  // -----------------------------------------------------------------------
  // Build <th> headers for a given tab
  // -----------------------------------------------------------------------
  _build_table_headers(tab) {
    const common = `
      <th>${__("UID")}</th>
      <th>${__("Patient")}</th>
      <th>${__("Accession")}</th>
      <th>${__("Mod")}</th>
      <th>${__("Scheduled")}</th>
      <th>${__("State")}</th>
    `;

    if (tab === "open") {
      return common + `<th>${__("Priority")}</th><th>${__("Protocol")}</th>`;
    }
    if (tab === "assigned") {
      return common + `<th>${__("Assigned Performer")}</th>`;
    }
    if (tab === "in_progress") {
      return common + `<th>${__("Claimed By")}</th><th>${__("Cancel Req?")}</th>`;
    }
    if (tab === "cancel_requested") {
      return common + `<th>${__("Claimed By")}</th><th>${__("Cancel Reason")}</th>`;
    }
    if (tab === "addendum") {
      return common + `<th>${__("Addendum For")}</th>`;
    }
    return common + `<th>${__("Claimed By")}</th>`;
  },

  // -----------------------------------------------------------------------
  // Build <td> cells for a given tab
  // -----------------------------------------------------------------------
  _build_row_cells(item, tab) {
    const badgeColor = STATE_BADGE[item.ups_state] || "gray";

    const uid_cell = `<td><code title="${item.name}">${item.name.substring(0, 18)}\u2026</code></td>`;
    const patient_cell = `<td>${frappe.utils.escape_html(item.patient_name || "")}</td>`;
    const acc_cell = `<td>${frappe.utils.escape_html(item.accession_number || "")}</td>`;
    const mod_cell = `<td>${frappe.utils.escape_html(item.modality || "")}</td>`;
    const sched_cell = `<td>${frappe.datetime.str_to_user(item.scheduled_datetime) || ""}</td>`;
    const state_cell = `<td><span class="indicator ${badgeColor}">${item.ups_state}</span></td>`;
    const common = uid_cell + patient_cell + acc_cell + mod_cell + sched_cell + state_cell;

    if (tab === "open") {
      return (
        common +
        `<td>${frappe.utils.escape_html(item.priority || "")}</td>` +
        `<td>${frappe.utils.escape_html(item.protocol_name || "")}</td>`
      );
    }
    if (tab === "assigned") {
      return (
        common +
        `<td><strong>${frappe.utils.escape_html(item.scheduled_performer_aet || "&#8212;")}</strong></td>`
      );
    }
    if (tab === "in_progress") {
      const cancelFlag = item.cancel_requested_at
        ? `<span class="badge badge-danger"
               title="${frappe.utils.escape_html(item.cancel_request_reason || "")}">${__("Pending")}</span>`
        : "";
      return (
        common +
        `<td>${frappe.utils.escape_html(item.claimed_by || "")}</td>` +
        `<td>${cancelFlag}</td>`
      );
    }
    if (tab === "cancel_requested") {
      return (
        common +
        `<td>${frappe.utils.escape_html(item.claimed_by || "")}</td>` +
        `<td><em>${frappe.utils.escape_html(item.cancel_request_reason || "")}</em></td>`
      );
    }
    if (tab === "addendum") {
      const addRef = item.addendum_for
        ? `<code title="${item.addendum_for}">${item.addendum_for.substring(0, 16)}\u2026</code>`
        : "&#8212;";
      return common + `<td>${addRef}</td>`;
    }
    return common + `<td>${frappe.utils.escape_html(item.claimed_by || "")}</td>`;
  },

  // -----------------------------------------------------------------------
  // Button event binding (all tabs)
  // -----------------------------------------------------------------------
  _bind_action_buttons($table) {
    const self = this;

    $table.off("click.ups").on("click.ups", ".ups-btn-claim", function () {
      self._claim($(this).data("uid"));
    });
    $table.on("click.ups", ".ups-btn-complete", function () {
      self._complete($(this).data("uid"));
    });
    $table.on("click.ups", ".ups-btn-history", function () {
      self._show_history($(this).data("uid"));
    });
    // UC2/UC4 — assign to specific performer
    $table.on("click.ups", ".ups-btn-assign", function () {
      self._assign($(this).data("uid"));
    });
    // UC5 — cancel-request advisory (task requester / supervisor perspective)
    $table.on("click.ups", ".ups-btn-request-cancel", function () {
      self._request_cancel($(this).data("uid"));
    });
    // UC6 — performer self-cancel (failure use case)
    $table.on("click.ups", ".ups-btn-performer-cancel", function () {
      self._performer_cancel($(this).data("uid"));
    });
    // UC3 — create addendum workitem
    $table.on("click.ups", ".ups-btn-addendum", function () {
      self._create_addendum($(this).data("uid"));
    });
    // Supervisor reschedule (T030)
    $table.on("click.ups", ".ups-btn-reschedule", function () {
      self._supervisor_reschedule($(this).data("uid"));
    });
    // Row click opens detail panel (not last-child actions cell)
    $table.on("click.ups", "tr.ups-row td:not(:last-child)", function () {
      const uid = $(this).closest("tr").data("uid");
      self._show_detail(uid);
    });
  },

  // -----------------------------------------------------------------------
  // UC1 — Claim (T024 + T025 409-conflict rollback)
  // -----------------------------------------------------------------------
  _claim(uid) {
    const self = this;
    const $row = $(`tr.ups-row[data-uid="${uid}"]`);

    // Optimistic UI update
    $row.find(".indicator").removeClass("blue").addClass("orange").text("IN PROGRESS");
    $row.find(".ups-btn-claim").prop("disabled", true).text(__("Claiming\u2026"));

    frappe.call({
      method: `${API}.claim_workitem`,
      args: { ups_uid: uid },
      callback: (r) => {
        if (!r.message) return;
        const res = r.message;

        if (!res.success) {
          // T025: roll back on 409 conflict
          $row.find(".indicator").removeClass("orange").addClass("blue").text("SCHEDULED");
          $row.find(".ups-btn-claim").prop("disabled", false).text(__("Claim"));
          frappe.msgprint({
            title: __("Claim Failed"),
            indicator: "orange",
            message: res.message || __("This step has already been claimed."),
          });
          self._refresh_row(uid);
        } else {
          self._load_worklist();
          self._load_summary();
        }
      },
      error: () => {
        $row.find(".indicator").removeClass("orange").addClass("blue").text("SCHEDULED");
        $row.find(".ups-btn-claim").prop("disabled", false).text(__("Claim"));
      },
    });
  },

  // -----------------------------------------------------------------------
  // Complete (T024)
  // -----------------------------------------------------------------------
  _complete(uid) {
    const self = this;

    frappe.prompt(
      {
        label: __("Performed Study UID (optional)"),
        fieldname: "performed_study_uid",
        fieldtype: "Data",
      },
      (values) => {
        frappe.call({
          method: `${API}.complete_workitem`,
          args: { ups_uid: uid, performed_study_uid: values.performed_study_uid },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({ message: __("Workitem completed."), indicator: "green" });
              self._load_worklist();
              self._load_summary();
            }
          },
        });
      },
      __("Complete Workitem"),
      __("Complete")
    );
  },

  // -----------------------------------------------------------------------
  // UC2/UC4 — Assign workitem to a specific Task Performer
  // -----------------------------------------------------------------------
  _assign(uid) {
    const self = this;

    // Find the workitem in the current data to read its Scheduled Station Class
    // Code Sequence (0040,4026).  This narrows the dropdown to only compatible
    // stations (e.g. only CT scanners for a CT workitem).
    const item = (this._worklist_data || []).find((w) => w.name === uid);
    const stationClassCode = item && item.scheduled_station_class_code;

    // Filter AE Mappings by station_class_code when available.
    // Falls back to all active mappings when the workitem has no class code or
    // no AE Mapping carries that class.
    const classMappings = stationClassCode
      ? this._ae_mappings.filter((m) => m.active !== 0 && m.station_class_code === stationClassCode)
      : [];
    const aet_mappings = classMappings.length
      ? classMappings
      : this._ae_mappings.filter((m) => m.active !== 0);
    const aet_options = aet_mappings.map((m) => m.ae_title);

    if (!aet_options.length) {
      frappe.msgprint({
        title: __("No AE Titles configured"),
        message: __("Please configure AE Mappings before assigning workitems."),
      });
      return;
    }

    // Build a human-readable hint about why the list is filtered
    let classHint = "";
    if (stationClassCode) {
      classHint = classMappings.length
        ? __(" Filtered to class \u00ab{0}\u00bb (0040,4026).", [stationClassCode])
        : __(" Class \u00ab{0}\u00bb (0040,4026) matched no stations \u2014 showing all.", [stationClassCode]);
    }

    frappe.prompt(
      [
        {
          label: __("Performer Station (AE Title)"),
          fieldname: "performer_aet",
          fieldtype: "Select",
          options: aet_options.join("\n"),
          reqd: 1,
          description: __(
            "Sets Scheduled Station Name Code Sequence (0040,4025) on this workitem. " +
              "The station must still claim the workitem to begin (IHE RRR-WF UC2/UC4)."
          ) + classHint,
        },
        {
          label: __("Reason / Notes (optional)"),
          fieldname: "reason",
          fieldtype: "Data",
        },
      ],
      (values) => {
        frappe.call({
          method: `${API}.assign_workitem`,
          args: {
            ups_uid: uid,
            performer_aet: values.performer_aet,
            reason: values.reason,
          },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({
                message: __("Workitem assigned to {0}.", [values.performer_aet]),
                indicator: "green",
              });
              self._load_worklist();
            }
          },
        });
      },
      __("Assign Workitem \u2014 UC2 / UC4"),
      __("Assign")
    );
  },

  // -----------------------------------------------------------------------
  // UC5 — Request cancellation (Task Requester / Supervisor advisory)
  // -----------------------------------------------------------------------
  _request_cancel(uid) {
    const self = this;
    frappe.prompt(
      {
        label: __("Reason for cancellation request"),
        fieldname: "reason",
        fieldtype: "Data",
        reqd: 1,
        description: __(
          "SCHEDULED workitems are cancelled immediately. " +
            "IN PROGRESS workitems: an advisory is sent to the performer \u2014 " +
            "the workitem stays IN PROGRESS until the performer acts (IHE RRR-WF UC5)."
        ),
      },
      (values) => {
        frappe.call({
          method: `${API}.request_workitem_cancel`,
          args: { ups_uid: uid, reason: values.reason },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({
                message: r.message.cancel_requested
                  ? __("Cancel request sent to performer. Awaiting performer action.")
                  : __("Workitem cancelled."),
                indicator: r.message.cancel_requested ? "orange" : "green",
              });
              self._load_worklist();
              self._load_summary();
            }
          },
        });
      },
      __("Request Cancellation \u2014 UC5"),
      __("Send Request")
    );
  },

  // -----------------------------------------------------------------------
  // UC6 — Performer self-cancel due to local failure
  // -----------------------------------------------------------------------
  _performer_cancel(uid) {
    const self = this;
    frappe.prompt(
      {
        label: __("Failure reason"),
        fieldname: "reason",
        fieldtype: "Data",
        reqd: 1,
        description: __(
          "Describe why you are unable to complete this read (IHE RRR-WF UC6). " +
            "The Task Requester will be notified and may create a replacement task."
        ),
      },
      (values) => {
        frappe.call({
          method: `${API}.performer_cancel_workitem`,
          args: { ups_uid: uid, reason: values.reason },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({
                message: __("Workitem cancelled (Failure UC6). Task Requester notified."),
                indicator: "orange",
              });
              self._load_worklist();
              self._load_summary();
            }
          },
        });
      },
      __("Cancel Workitem \u2014 Failure (UC6)"),
      __("Cancel")
    );
  },

  // -----------------------------------------------------------------------
  // UC3 — Create addendum workitem for a follow-up read
  // -----------------------------------------------------------------------
  _create_addendum(uid) {
    const self = this;
    frappe.prompt(
      [
        {
          label: __("Reason for addendum"),
          fieldname: "reason",
          fieldtype: "Data",
          reqd: 1,
          description: __(
            "Describe the gap or correction in the original report (IHE RRR-WF UC3). " +
              "A new SCHEDULED workitem will be created referencing this original."
          ),
        },
        {
          label: __("Priority"),
          fieldname: "priority",
          fieldtype: "Select",
          options: "HIGH\nMEDIUM\nLOW",
          default: "MEDIUM",
          reqd: 1,
        },
      ],
      (values) => {
        frappe.call({
          method: `${API}.create_addendum_workitem`,
          args: {
            original_uid: uid,
            reason: values.reason,
            priority: values.priority,
          },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({ message: __("Addendum workitem created."), indicator: "green" });
              frappe.msgprint({
                title: __("Report Addendum Created \u2014 UC3"),
                indicator: "green",
                message: `
                  <p>${__("New addendum workitem UID:")}</p>
                  <code style="word-break:break-all;">${r.message.addendum_uid}</code>
                  <p class="mt-2 text-muted">
                    ${__("The workitem is now SCHEDULED. Switch to the Open Worklist tab to claim it.")}
                  </p>`,
              });
              self._load_worklist();
              self._load_summary();
            }
          },
        });
      },
      __("Create Report Addendum \u2014 UC3"),
      __("Create Addendum")
    );
  },

  // -----------------------------------------------------------------------
  // Legacy supervisor actions (T029 — used in the "all" tab rows)
  // -----------------------------------------------------------------------
  _bind_legacy_supervisor_buttons() {
    const self = this;
    $("#ups-worklist-table")
      .on("click.sup", ".ups-btn-cancel", function () {
        self._supervisor_cancel($(this).data("uid"));
      })
      .on("click.sup", ".ups-btn-reassign", function () {
        self._supervisor_reassign($(this).data("uid"));
      });
  },

  _supervisor_cancel(uid) {
    const self = this;
    frappe.prompt(
      {
        label: __("Reason for cancellation"),
        fieldname: "reason",
        fieldtype: "Data",
        reqd: 1,
      },
      (values) => {
        frappe.call({
          method: `${API}.cancel_workitem`,
          args: { ups_uid: uid, reason: values.reason },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({ message: __("Workitem cancelled."), indicator: "green" });
              self._load_worklist();
              self._load_summary();
            }
          },
        });
      },
      __("Cancel Workitem"),
      __("Cancel Workitem")
    );
  },

  _supervisor_reassign(uid) {
    const self = this;
    const aet_options = this._ae_mappings
      .filter((m) => m.active !== 0)
      .map((m) => m.ae_title);

    frappe.prompt(
      {
        label: __("New AE Title"),
        fieldname: "new_aet",
        fieldtype: "Select",
        options: aet_options.join("\n"),
        reqd: 1,
      },
      (values) => {
        frappe.call({
          method: `${API}.reassign_workitem`,
          args: { ups_uid: uid, new_aet: values.new_aet },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({ message: __("Workitem reassigned."), indicator: "green" });
              self._load_worklist();
            }
          },
        });
      },
      __("Reassign Workitem"),
      __("Reassign")
    );
  },

  _supervisor_reschedule(uid) {
    const self = this;
    frappe.confirm(
      __("Reschedule workitem {0} back to SCHEDULED via dcm4chee proprietary endpoint?", [uid]),
      () => {
        frappe.call({
          method: `${API}.reschedule_workitem`,
          args: { ups_uid: uid },
          callback: (r) => {
            if (r.message && r.message.success) {
              frappe.show_alert({ message: __("Workitem rescheduled."), indicator: "green" });
              self._load_worklist();
              self._load_summary();
            }
          },
        });
      }
    );
  },

  // -----------------------------------------------------------------------
  // Detail panel — single workitem expanded view
  // -----------------------------------------------------------------------
  _show_detail(uid) {
    this._selected_uid = uid;
    const self = this;

    $("#ups-table-col").removeClass("col-12").addClass("col-sm-8");
    $("#ups-detail-col").show();

    frappe.call({
      method: `${API}.get_workitem`,
      args: { ups_uid: uid },
      callback: (r) => {
        if (!r.message) return;
        const item = r.message;
        const $panel = $("#ups-detail-panel");

        const cancelBlock = item.cancel_requested_at
          ? `<div class="alert alert-danger py-1 mb-2">
               <strong>${__("Cancel Requested")}:</strong>
               ${frappe.datetime.str_to_user(item.cancel_requested_at) || ""}
               &mdash; ${frappe.utils.escape_html(item.cancel_request_reason || "")}
             </div>`
          : "";

        const addendumBlock = item.addendum_for
          ? `<p><strong>${__("Addendum for")}:</strong>
               <code>${frappe.utils.escape_html(item.addendum_for)}</code></p>`
          : "";

        $panel.html(`
          <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
              <strong>${__("Workitem Details")}</strong>
              <div>
                <span class="indicator ${STATE_BADGE[item.ups_state] || "gray"}">${item.ups_state}</span>
                <button class="btn btn-xs btn-default ml-2"
                        id="ups-btn-close-detail"
                        title="${__("Close")}">&#x2715;</button>
              </div>
            </div>
            <div class="card-body">
              ${cancelBlock}
              <p><strong>${__("UID")}:</strong> <code style="word-break:break-all;">${item.name}</code></p>
              ${addendumBlock}
              <p><strong>${__("Patient")}:</strong>
                 ${frappe.utils.escape_html(item.patient_name || "")}
                 (${frappe.utils.escape_html(item.patient_id || "")})</p>
              <p><strong>${__("Accession")}:</strong>
                 ${frappe.utils.escape_html(item.accession_number || "")}</p>
              <p><strong>${__("Proc ID")}:</strong>
                 ${frappe.utils.escape_html(item.requested_procedure_id || "")}</p>
              <p><strong>${__("Modality")}:</strong>
                 ${frappe.utils.escape_html(item.modality || "")}</p>
              <p><strong>${__("Priority")}:</strong>
                 ${frappe.utils.escape_html(item.priority || "")}</p>
              <p><strong>${__("Scheduled")}:</strong>
                 ${frappe.datetime.str_to_user(item.scheduled_datetime) || ""}</p>
              <p><strong>${__("Scheduled Performer")}:</strong>
                 ${frappe.utils.escape_html(item.scheduled_performer_aet || "&#8212;")}</p>
              <p><strong>${__("Claimed By")}:</strong>
                 ${frappe.utils.escape_html(item.claimed_by || "&#8212;")}</p>
              <hr>
              <button class="btn btn-sm btn-default"
                      id="ups-btn-show-history">${__("Event History")}</button>
              <button class="btn btn-sm btn-default ml-1"
                      id="ups-btn-export-csv">${__("Export CSV")}</button>
            </div>
          </div>
        `);

        $panel.find("#ups-btn-close-detail").on("click", () => {
          $("#ups-detail-col").hide();
          $("#ups-table-col").removeClass("col-sm-8").addClass("col-12");
          $("#ups-detail-panel").empty();
          self._selected_uid = null;
        });
        $panel.find("#ups-btn-show-history").on("click", () => self._show_history(uid));
        $panel.find("#ups-btn-export-csv").on("click", () => {
          const url = `/api/method/${API}.export_audit_log?ups_uid=${encodeURIComponent(uid)}&fmt=csv`;
          window.open(url, "_blank");
        });
      },
    });
  },

  // -----------------------------------------------------------------------
  // Event history / Audit (T035)
  // -----------------------------------------------------------------------
  _show_history(uid) {
    frappe.call({
      method: `${API}.get_event_history`,
      args: { ups_uid: uid },
      callback: (r) => {
        if (!r.message) return;
        const events = r.message.events || [];

        const rows = events
          .map(
            (e) => `
            <tr>
              <td>${frappe.datetime.str_to_user(e.event_timestamp) || ""}</td>
              <td>${frappe.utils.escape_html(e.actor || "")}</td>
              <td><strong>${e.event_type}</strong></td>
              <td>${e.old_state ? `${e.old_state} &rarr; ${e.new_state}` : e.new_state || ""}</td>
              <td>${frappe.utils.escape_html(e.details || "")}</td>
            </tr>
          `
          )
          .join("");

        const exportUrl = `/api/method/${API}.export_audit_log?ups_uid=${encodeURIComponent(uid)}&fmt=csv`;
        const exportJsonUrl = `/api/method/${API}.export_audit_log?ups_uid=${encodeURIComponent(uid)}&fmt=json`;

        frappe.msgprint({
          title: __("Event History: {0}", [uid.substring(0, 20) + "\u2026"]),
          indicator: "blue",
          message: `
            <div style="max-height:400px;overflow-y:auto;">
              <table class="table table-sm table-bordered">
                <thead><tr>
                  <th>${__("Timestamp")}</th>
                  <th>${__("Actor")}</th>
                  <th>${__("Event")}</th>
                  <th>${__("Transition")}</th>
                  <th>${__("Details")}</th>
                </tr></thead>
                <tbody>${rows || `<tr><td colspan="5" class="text-muted">${__("No events.")}</td></tr>`}</tbody>
              </table>
              <a href="${exportUrl}" target="_blank"
                 class="btn btn-sm btn-default">${__("Export CSV")}</a>
              <a href="${exportJsonUrl}" target="_blank"
                 class="btn btn-sm btn-default ml-1">${__("Export JSON")}</a>
            </div>
          `,
        });
      },
    });
  },

  // -----------------------------------------------------------------------
  // Reconciliation panel (T036)
  // -----------------------------------------------------------------------
  _show_reconciliation() {
    const self = this;
    const $container = $("#ups-reconciliation-container");
    $container.show().html(
      `<div class="text-muted">${__("Running reconciliation against dcm4chee-arc\u2026")}</div>`
    );

    frappe.call({
      method: `${API}.get_reconciliation_diff`,
      callback: (r) => {
        if (!r.message) return;
        const { discrepancies, total } = r.message;

        if (!total) {
          $container.html(
            `<div class="alert alert-success">${__(
              "No discrepancies found \u2014 local mirror is in sync with dcm4chee-arc."
            )}</div>`
          );
          return;
        }

        const rows = discrepancies
          .map(
            (d) => `
            <tr>
              <td><code>${d.ups_uid}</code></td>
              <td><span class="badge badge-warning">${d.issue_type}</span></td>
              <td>${d.local_state || "&#8212;"}</td>
              <td>${d.remote_state || "&#8212;"}</td>
              <td>${frappe.utils.escape_html(d.recommended_action || "")}</td>
              <td>
                <button class="btn btn-xs btn-primary ups-btn-accept-remote"
                        data-uid="${d.ups_uid}">${__("Accept Remote")}</button>
              </td>
            </tr>
          `
          )
          .join("");

        $container.html(`
          <div class="card">
            <div class="card-header">
              <strong>${__("Reconciliation Results")} &mdash; ${total} ${__("discrepancies")}</strong>
              <button class="btn btn-xs btn-default pull-right"
                      id="ups-btn-close-recon">${__("Close")}</button>
            </div>
            <div class="card-body" style="max-height:400px;overflow-y:auto;">
              <table class="table table-sm table-bordered">
                <thead><tr>
                  <th>${__("UPS UID")}</th>
                  <th>${__("Issue")}</th>
                  <th>${__("Local State")}</th>
                  <th>${__("Remote State")}</th>
                  <th>${__("Recommended Action")}</th>
                  <th>${__("Action")}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </div>
        `);

        $container.on("click", ".ups-btn-accept-remote", function () {
          const uid = $(this).data("uid");
          frappe.call({
            method: `${API}.accept_reconciliation_item`,
            args: { ups_uid: uid, action: "accept_remote" },
            callback: (r2) => {
              if (r2.message && r2.message.success) {
                frappe.show_alert({
                  message: __("Accepted remote state for {0}", [uid]),
                  indicator: "green",
                });
                self._show_reconciliation();
                self._load_worklist();
              }
            },
          });
        });

        $container.on("click", "#ups-btn-close-recon", () => {
          $container.hide().empty();
        });
      },
    });
  },

  // -----------------------------------------------------------------------
  // Refresh a single table row without full reload
  // -----------------------------------------------------------------------
  _refresh_row(uid) {
    const self = this;
    frappe.call({
      method: `${API}.get_workitem`,
      args: { ups_uid: uid },
      callback: (r) => {
        if (!r.message) return;
        const item = r.message;
        const $row = $(`tr.ups-row[data-uid="${uid}"]`);
        const badgeColor = STATE_BADGE[item.ups_state] || "gray";
        $row
          .find(".indicator")
          .removeClass("blue orange green gray")
          .addClass(badgeColor)
          .text(item.ups_state);
      },
    });
  },

  // -----------------------------------------------------------------------
  // Realtime subscription (T024)
  // -----------------------------------------------------------------------
  _bind_realtime() {
    const self = this;
    frappe.realtime.on("ups_state_change", (data) => {
      if (data && data.ups_instance_uid) {
        self._refresh_row(data.ups_instance_uid);
      }
      self._load_summary();
    });
  },

  // -----------------------------------------------------------------------
  // Role helpers
  // -----------------------------------------------------------------------
  _isTechnologist() {
    return (
      this._current_user_roles.includes("UPS Technologist") ||
      this._current_user_roles.includes("UPS Supervisor") ||
      this._current_user_roles.includes("System Manager")
    );
  },
  _isSupervisor() {
    return (
      this._current_user_roles.includes("UPS Supervisor") ||
      this._current_user_roles.includes("System Manager")
    );
  },
  _isSupervisorOrEngineer() {
    return (
      this._isSupervisor() ||
      this._current_user_roles.includes("UPS Integration Engineer")
    );
  },
};
