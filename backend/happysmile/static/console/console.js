/* Staff console. Phase 2: Standard callback. Phase 3: Needs you, Booked by assistant, review, feedback, test calls. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var TREATMENT = { braces: "Braces / aligners", whitening: "Whitening", implants: "Implants", other: "Other" };
  var LANG = { en: "English", hi: "Hindi" };
  var STATUS = {
    awaiting_call: ["Not called yet", "tag-warn"], no_answer: ["Called, no answer", ""], follow_up: ["Reached, follow up", "tag-info"],
    booked: ["Booked", "tag-ok"], not_interested: ["Not interested", ""], unreachable: ["Wrong number", ""],
    queued: ["Assistant calling soon", "tag-info"], needs_you: ["Needs you", "tag-warn"], whatsapp_sent: ["WhatsApp sent", "tag-info"]
  };
  var MSG_STATUS = { queued: "Queued", sending: "Sending", sent: "Sent", delivered: "Delivered", read: "Read", failed: "Not delivered",
    received: "Received", cancelled: "Cancelled" };
  var TEMPLATE_NAMES = { enquiry_ack_v1: "Acknowledgement", whatsapp_hello_v1: "WhatsApp hello", booking_confirm_v1: "Booking confirmation",
    no_answer_v1: "Couldn't reach you", call_reminder_v1: "Call reminder", booking_update_v1: "Booking update", opt_out_confirm_v1: "Opt-out confirmation",
    appointment_reminder_v1: "Appointment reminder", no_show_v1: "Missed you" };
  var TAGS = {
    asked_person: ["Asked for a person", "tag-info"], pain_swelling: ["Pain or swelling (urgent)", "tag-urgent"],
    emergency: ["Emergency symptoms", "tag-urgent"], distress: ["Distress", "tag-urgent"], price_emi: ["Price/EMI question", "tag-warn"],
    clinical: ["Clinical question", "tag-primary"], couldnt_understand: ["Couldn't understand", ""], no_suitable_slot: ["No suitable slot", ""],
    minor: ["Under 18", "tag-info"], recording_objection: ["Didn't want recording", ""], needs_staff: ["Needs staff help", ""],
    not_reached: ["Not reached (3 calls)", ""], system_fallback: ["System fallback", ""], booking_cancelled: ["Booking cancelled", "tag-warn"],
    abusive: ["Ended: abusive caller", ""], whatsapp_reply: ["WhatsApp reply", "tag-ok"], whatsapp_preferred: ["Prefers WhatsApp", "tag-ok"],
    whatsapp_failed: ["WhatsApp not delivered", "tag-warn"], booking_paused: ["AI booking paused", "tag-warn"],
    no_show: ["Missed consultation", "tag-warn"], transferred: ["Transferred live", "tag-ok"]
  };
  var ARM = { control: "Standard callback group", assistant: "Assistant group", not_in_pilot: "Not in pilot" };
  var HELP = {
    needs_you: "Handed over by the assistant. Urgent first, then longest wait. Target: 5 minutes for urgent, 15 minutes for the rest.",
    booked: "Consultations the assistant booked. Review every booking before the appointment.",
    no_answer: "The assistant couldn't reach these people. It retries after 5 minutes and 2 hours, then sends a WhatsApp message. Replies move to Needs you.",
    standard: "Call these people as you normally would, then record what happened. This is how we measure today's process."
  };
  var FEEDBACK_REASONS = ["Assistant could have handled this", "Should have been urgent", "Wrong reason tag", "Other"];

  var state = { me: null, tab: "needs_you", view: "to_call", clinic: "all", leads: [], needs: [], booked: [], noanswer: [],
    selected: null, detail: null, metrics: null };
  var es = null, refreshTimer = null;

  // ---------------------------------------------------------------- helpers
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function api(path, opts) {
    opts = opts || {};
    var headers = { Accept: "application/json" };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (opts.method && opts.method !== "GET") headers["X-Requested-With"] = "hs-console";
    return fetch(path, { method: opts.method || "GET", headers: headers, credentials: "same-origin",
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 401 && path !== "/v1/auth/login") { showLogin(); }
          if (!r.ok) {
            var msg = typeof j.detail === "string" ? j.detail : (j.message || "Request failed");
            var e = new Error(msg); e.status = r.status; throw e;
          }
          return j;
        });
      });
  }
  function clock(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit" });
  }
  function dayTime(iso) {
    return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  }
  function ago(iso) {
    var m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    return m < 60 ? m + " min ago" : m < 1440 ? Math.floor(m / 60) + " h " + (m % 60) + " min ago" : Math.floor(m / 1440) + " days ago";
  }
  function mmss(sec) { sec = Math.max(0, Math.floor(sec)); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
  function contactPref(l) {
    if (l.contact_pref === "whatsapp") return "Prefers WhatsApp";
    if (l.contact_pref === "scheduled") return "Call at " + dayTime(l.scheduled_at);
    return "Call back";
  }
  function tag(key) { var t = TAGS[key] || [key, ""]; return '<span class="tag ' + t[1] + '">' + esc(t[0]) + "</span>"; }
  function toast(msg) {
    var el = document.createElement("div"); el.className = "toast"; el.textContent = msg;
    $("toasts").appendChild(el); setTimeout(function () { el.remove(); }, 5000);
  }
  function showError(e) { if (e && e.status !== 401) toast(e.message || "Something went wrong."); }

  // SLA timer: text + bar, so it doesn't rely on colour alone.
  function sla(handedIso, minutes, claimedIso) {
    var target = minutes * 60;
    if (claimedIso) return { cls: "sla-claimed", pct: 100, text: "Picked up after " + mmss((Date.parse(claimedIso) - Date.parse(handedIso)) / 1000) };
    var waited = (Date.now() - Date.parse(handedIso)) / 1000, r = waited / target;
    if (r >= 1) return { cls: "sla-over", pct: 100, text: "Over target by " + mmss(waited - target) + " (target " + minutes + " min)" };
    if (r >= 0.7) return { cls: "sla-soon", pct: r * 100, text: "Due soon: " + mmss(waited) + " of " + minutes + " min" };
    return { cls: "sla-ok", pct: r * 100, text: mmss(waited) + " of " + minutes + " min" };
  }
  function slaHtml(handed, minutes, claimed) {
    return '<div class="sla" data-sla="1" data-handed="' + esc(handed) + '" data-min="' + minutes + '" data-claimed="' + esc(claimed || "") +
      '"><span class="sla-text"></span><div class="sla-bar"><div class="sla-fill"></div></div></div>';
  }
  function paintSla() {
    document.querySelectorAll("[data-sla]").forEach(function (el) {
      var s = sla(el.dataset.handed, +el.dataset.min, el.dataset.claimed || null);
      el.className = "sla " + s.cls;
      el.querySelector(".sla-text").textContent = s.text;
      el.querySelector(".sla-fill").style.width = s.pct.toFixed(1) + "%";  // CSSOM, allowed by the CSP
    });
  }

  // ---------------------------------------------------------------- auth
  function showLogin() {
    if (es) { es.close(); es = null; }
    $("app-view").hidden = true; $("login-view").hidden = false; $("username").focus();
  }
  $("login-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var err = $("login-error"); err.hidden = true; $("login-btn").disabled = true;
    api("/v1/auth/login", { method: "POST", body: { username: $("username").value, password: $("password").value } })
      .then(function (me) { $("password").value = ""; start(me); })
      .catch(function (ex) { err.textContent = ex.message; err.hidden = false; })
      .then(function () { $("login-btn").disabled = false; });
  });
  $("logout").addEventListener("click", function () {
    // On the open demo console, signing out drops back to the demo visitor instead of the login form.
    var after = function () { api("/v1/auth/me").then(start).catch(showLogin); };
    api("/v1/auth/logout", { method: "POST" }).then(after, after);
  });

  function start(me) {
    state.me = me;
    $("login-view").hidden = true; $("app-view").hidden = false;
    $("user").textContent = me.name + " (" + me.role.replace("_", " ") + ")";
    $("ops-btn").hidden = me.role === "front_desk";
    $("logout").hidden = me.username === "guest";  // open demo console: nobody to sign out
    loadTransfer();
    var sel = $("clinic-filter"); sel.innerHTML = "";
    if (me.clinics.length > 1) sel.appendChild(new Option("All my clinics", "all"));
    me.clinics.forEach(function (c) { sel.appendChild(new Option(c.name, c.id)); });
    state.clinic = sel.value;
    renderTabs(); refresh(); connectStream();
  }

  // ---------------------------------------------------------------- data
  function refresh() {
    var q = "clinic=" + encodeURIComponent(state.clinic);
    return Promise.all([
      api("/v1/metrics/today?" + q).then(function (m) { state.metrics = m; renderStrip(); }),
      api("/v1/queue?tab=needs_you&" + q).then(function (r) { state.needs = r.items; }),
      api("/v1/queue?tab=booked&" + q).then(function (r) { state.booked = r.items; }),
      api("/v1/queue?tab=no_answer&" + q).then(function (r) { state.noanswer = r.items; }),
      api("/v1/leads?" + q + "&view=" + (state.tab === "standard" ? state.view : "to_call")).then(function (r) { state.leads = r.leads; })
    ]).then(function () {
      renderCounts(); renderList();
      return state.selected ? loadDetail(state.selected) : null;
    }).catch(showError);
  }
  function scheduleRefresh() { clearTimeout(refreshTimer); refreshTimer = setTimeout(refresh, 300); }

  function connectStream() {
    if (es) es.close();
    es = new EventSource("/v1/stream");
    es.addEventListener("open", function () { $("live").className = "live on"; $("live").title = "Live updates on"; $("banner").hidden = true; });
    es.addEventListener("change", scheduleRefresh);
    es.addEventListener("error", function () {
      $("live").className = "live off"; $("live").title = "Reconnecting";
      $("banner").textContent = "Reconnecting to live updates. The list may be out of date for a moment."; $("banner").hidden = false;
      api("/v1/auth/me").catch(function () {});
    });
  }

  // ---------------------------------------------------------------- strip + tabs
  function renderStrip() {
    var m = state.metrics; if (!m) return;
    var a = m.reached_within_5.assistant, c = m.reached_within_5.control;
    var pct = function (x) { return x.leads ? Math.round(100 * x.reached_within_5 / x.leads) + "%" : "–"; };
    var scope = state.clinic === "all" ? "your clinics" : $("clinic-filter").selectedOptions[0].textContent;
    var over = state.needs.filter(function (n) { return !n.claimed_at && Date.now() > Date.parse(n.sla_due_at); }).length;
    var stats = [
      ["Enquiries received", m.enquiries_received, "Today, " + scope],
      ["Reached within 5 minutes", pct(a), a.leads ? a.reached_within_5 + " of " + a.leads + " assistant-group leads" :
        "Standard callback: " + c.reached_within_5 + " of " + c.leads, !a.leads],
      ["Consults booked by assistant", m.booked_by_assistant, "Booked by staff today: " + m.booked_by_staff],
      ["Waiting for staff", m.waiting_for_staff, over ? over + " over target" : "All within target", false, over > 0],
      ["No answer (retrying)", m.no_answer, "Standard callback, to call again"]
    ];
    $("strip").innerHTML = stats.map(function (s) {
      return '<div class="stat"><div class="stat-label">' + esc(s[0]) + '</div><div class="stat-value' + (s[3] ? " muted" : "") + '">' +
        esc(s[1]) + '</div><div class="stat-sub' + (s[4] ? " alert" : "") + '">' + esc(s[2]) + "</div></div>";
    }).join("");
  }
  function renderCounts() {
    $("tab-needs_you").querySelector(".count").textContent = state.needs.length;
    $("tab-booked").querySelector(".count").textContent = state.booked.length;
    $("tab-no_answer").querySelector(".count").textContent = state.noanswer.length;
    if (state.tab !== "standard" || state.view === "to_call") $("tab-standard").querySelector(".count").textContent =
      state.tab === "standard" ? state.leads.length : (state.metrics ? state.metrics.waiting_for_staff - state.needs.length + state.metrics.no_answer : 0);
    renderStrip();
  }
  function renderTabs() {
    document.querySelectorAll('#tabs [role="tab"]').forEach(function (b) {
      var sel = b.dataset.tab === state.tab;
      b.setAttribute("aria-selected", sel); b.tabIndex = sel ? 0 : -1;
    });
    $("list-pane").setAttribute("aria-labelledby", "tab-" + state.tab);
    $("tab-help").textContent = HELP[state.tab];
    $("view-toggle").hidden = state.tab !== "standard";
  }
  function switchTab(tab) {
    state.tab = tab; state.selected = null; state.detail = null;
    renderTabs(); renderPanel(); renderList();  // draw from cached data at once, so stale rows can't be clicked
    refresh();
  }
  $("tabs").addEventListener("click", function (e) { var b = e.target.closest('[role="tab"]'); if (b) switchTab(b.dataset.tab); });
  $("tabs").addEventListener("keydown", function (e) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    var tabs = Array.prototype.slice.call(this.querySelectorAll('[role="tab"]'));
    var i = tabs.findIndex(function (t) { return t.dataset.tab === state.tab; });
    var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    switchTab(next.dataset.tab); next.focus();
  });
  $("view-toggle").addEventListener("change", function (e) { state.view = e.target.value; state.selected = null; state.detail = null; renderPanel(); refresh(); });
  $("clinic-filter").addEventListener("change", function () { state.clinic = this.value; state.selected = null; state.detail = null; renderPanel(); refresh(); });

  // ---------------------------------------------------------------- lists
  function leadCell(id, name, meta) {
    return '<div><button class="name-btn" type="button" data-open="' + esc(id) + '"><span class="lead-name">' + esc(name) + "</span></button>" +
      '<span class="lead-meta">' + esc(meta) + "</span></div>";
  }
  function rowWrap(tab, id, cells) {
    return '<div class="row cols-' + tab + '" data-row="' + esc(id) + '"' + (id === state.selected ? ' aria-current="true"' : "") + ">" + cells + "</div>";
  }
  function emptyHtml(a, b) { return '<div class="empty"><strong>' + esc(a) + "</strong>" + esc(b) + "</div>"; }

  function renderList() {
    var list = $("list"), t = state.tab;
    if (t === "no_answer") {
      if (!state.noanswer.length) { list.innerHTML = emptyHtml("Everyone has been reached.", "People the assistant can't reach appear here."); return; }
      list.innerHTML = '<div class="row-head cols-no_answer"><span>Lead</span><span>Attempts</span><span>Next step</span></div>' +
        state.noanswer.map(function (n) {
          var next = n.status === "whatsapp_sent"
            ? "WhatsApp sent " + clock(n.whatsapp_sent_at) + '<span class="cell-sub">' + esc(MSG_STATUS[n.whatsapp_status] || "Queued") + ", waiting for a reply</span>"
            : n.next_call ? "Next call " + clock(n.next_call) + '<span class="cell-sub" data-ago="' + esc(n.created_at) + '">Enquired ' + ago(n.created_at) + "</span>" : "Calling now";
          return rowWrap("no_answer", n.id, leadCell(n.id, n.name, TREATMENT[n.treatment] + " · " + n.clinic + " · " + LANG[n.language]) +
            "<div><strong>" + n.calls + " of 3 calls</strong><span class=\"cell-sub\">Last: " + esc((n.last_result || "").replace("_", " ")) + "</span></div><div>" + next + "</div>");
        }).join("");
      return;
    }
    if (t === "needs_you") {
      if (!state.needs.length) { list.innerHTML = emptyHtml("Nothing waiting.", "New handovers from the assistant will appear here."); return; }
      list.innerHTML = '<div class="row-head cols-needs_you"><span>Lead</span><span>Handover reason</span><span>Waiting vs target</span></div>' +
        state.needs.map(function (n) {
          return rowWrap("needs_you", n.id, leadCell(n.id, n.name, TREATMENT[n.treatment] + " · " + n.clinic + " · " + LANG[n.language]) +
            '<div class="cell-tags">' + n.tags.map(tag).join("") + (n.escalated ? '<span class="tag tag-urgent">Escalated</span>' : "") + "</div>" +
            "<div>" + slaHtml(n.handed_at, n.sla_minutes, n.claimed_at) + (n.claimed_by ? '<span class="cell-sub">' + esc(n.claimed_by) + " is calling</span>" : "") + "</div>");
        }).join("");
      paintSla(); return;
    }
    if (t === "booked") {
      if (!state.booked.length) { list.innerHTML = emptyHtml("No assistant bookings yet.", "Bookings appear here for review as soon as they are made."); return; }
      list.innerHTML = '<div class="row-head cols-booked"><span>Lead</span><span>Consultation</span><span>Dentist</span><span>Review</span></div>' +
        state.booked.map(function (b) {
          var rev = b.review_status === "pending" ? '<button class="btn btn-sm" type="button" data-review="' + esc(b.booking_id) + '" data-lead="' + esc(b.id) + '">Review</button>'
            : '<span class="tag tag-ok">' + (b.review_status === "changed" ? "Changed" : "Approved") + "</span>";
          return rowWrap("booked", b.id, leadCell(b.id, b.name, TREATMENT[b.treatment] + " · " + b.clinic + " · " + LANG[b.language]) +
            "<div><strong>" + esc(dayTime(b.start_at)) + "</strong></div><div>" + esc(b.dentist) + '<span class="cell-sub">' + esc(b.clinic) + "</span></div><div>" + rev + "</div>");
        }).join("");
      return;
    }
    if (!state.leads.length) {
      list.innerHTML = emptyHtml(state.view === "to_call" ? "Nobody waiting." : "Nothing closed yet.",
        state.view === "to_call" ? "New enquiries appear here within seconds." : "Booked and closed leads appear here.");
      return;
    }
    list.innerHTML = '<div class="row-head cols-standard"><span>Lead</span><span>Enquired</span><span>Contact</span><span>Status</span></div>' +
      state.leads.map(function (l) {
        var s = STATUS[l.status] || [l.status, ""];
        var extra = l.claimed_by ? '<span class="cell-sub">' + (l.claimed_by_me ? "You are calling" : esc(l.claimed_by) + " is calling") + "</span>"
          : l.attempts ? '<span class="cell-sub">' + l.attempts + (l.attempts === 1 ? " call" : " calls") + "</span>" : "";
        return rowWrap("standard", l.id, leadCell(l.id, l.name, TREATMENT[l.treatment] + " · " + l.clinic + " · " + LANG[l.language] + (l.returning ? " · Returning" : "")) +
          "<div>" + clock(l.created_at) + '<span class="cell-sub" data-ago="' + esc(l.created_at) + '">' + ago(l.created_at) + "</span></div>" +
          "<div>" + esc(contactPref(l)) + "</div>" + '<div><span class="tag ' + s[1] + '">' + esc(s[0]) + "</span>" + extra + "</div>");
      }).join("");
  }
  $("list").addEventListener("click", function (e) {
    var rv = e.target.closest("[data-review]");
    if (rv) { select(rv.dataset.lead, false).then(function () { openReview(rv.dataset.review); }); return; }
    var el = e.target.closest("[data-open]") || e.target.closest("[data-row]"); if (!el) return;
    select(el.dataset.open || el.dataset.row, true);
  });

  function select(id, focus) {
    state.selected = id; renderList();
    return loadDetail(id).then(function () { if (focus) $("panel").focus({ preventScroll: true }); });
  }
  function loadDetail(id) {
    return Promise.all([api("/v1/leads/" + id), api("/v1/leads/" + id + "/assistant")])
      .then(function (r) { state.detail = r[0]; state.detail.assistant = r[1]; renderPanel(); })
      .catch(function (e) { if (e.status === 404 || e.status === 403) { state.selected = null; state.detail = null; renderPanel(); } showError(e); });
  }

  // ---------------------------------------------------------------- panel
  function renderPanel() {
    var p = $("panel"), l = state.detail;
    if (!l) { p.classList.add("is-empty"); p.innerHTML = '<div class="panel-empty">Select a lead to see details and record the call.</div>'; return; }
    p.classList.remove("is-empty");
    var a = l.assistant || {}, ho = a.handover, conv = a.conversation, rev = a.booking_review;
    var s = STATUS[l.status] || [l.status, ""];
    var open = ["awaiting_call", "no_answer", "follow_up", "needs_you", "whatsapp_sent"].indexOf(l.status) >= 0;
    var tel = "tel:" + l.phone.replace(/\s/g, "");
    var h = [];
    h.push('<div class="panel-head"><div><h2>' + esc(l.name) + '</h2><a class="tel-link" href="' + esc(tel) + '">' + esc(l.phone) + "</a>" +
      '<div class="panel-badges"><span class="tag">' + esc(ARM[l.arm] || l.arm) + '</span><span class="tag">' + esc(LANG[l.language]) + "</span>" +
      '<span class="tag ' + s[1] + '">' + esc(s[0]) + "</span>" + (ho && ho.urgency === "urgent" ? '<span class="tag tag-urgent">Urgent</span>' : "") + "</div></div>" +
      '<button class="btn btn-sm icon-btn panel-close" type="button" data-action="close" aria-label="Close details">&times;</button></div>');
    var treatment = TREATMENT[l.treatment] + (l.treatment_other ? ": " + l.treatment_other : "") +
      (l.extra_treatments.length ? " (also asked about " + l.extra_treatments.map(function (x) { return TREATMENT[x]; }).join(", ") + ")" : "");
    h.push('<div class="panel-section"><dl class="facts">' +
      "<dt>Treatment</dt><dd>" + esc(treatment) + "</dd><dt>Clinic</dt><dd>" + esc(l.clinic) + "</dd>" +
      "<dt>Contact</dt><dd>" + esc(contactPref(l)) + "</dd>" +
      "<dt>Enquired</dt><dd>" + clock(l.created_at) + " (" + ago(l.created_at) + ")</dd>" +
      "<dt>First reached</dt><dd>" + (l.first_reached_at ? clock(l.first_reached_at) + " (" + Math.round((Date.parse(l.first_reached_at) - Date.parse(l.created_at)) / 60000) + " min after enquiry)" : "Not yet") + "</dd>" +
      "<dt>Reference</dt><dd>" + esc(l.ref) + "</dd></dl>" +
      (l.follow_up_note ? '<p class="notice notice-info">' + esc(l.follow_up_note) + "</p>" : "") + "</div>");

    if (ho) {
      var urgentNote = ho.tags.indexOf("pain_swelling") >= 0 ? '<p class="notice notice-urgent">Reports pain or swelling. Call now. The assistant gave safe-care advice and did not book.</p>' : "";
      h.push('<div class="panel-section"><h3>Handover</h3><div class="cell-tags">' + ho.tags.map(tag).join("") + "</div>" +
        slaHtml(ho.handed_at, ho.sla_minutes, ho.claimed_at) + urgentNote +
        '<p class="cell-sub">Patient was told: ' + (ho.promised === "morning" ? "someone will call first thing tomorrow morning." : "someone will call within " + ho.sla_minutes + " minutes.") + "</p></div>");
    }
    if (l.booking) {
      h.push('<div class="panel-section"><h3>Booking</h3><div class="booking-card"><div class="booking-slot">' + esc(dayTime(l.booking.start_at)) +
        "</div><div>" + esc(l.booking.dentist) + " · " + esc(l.clinic) + "</div><div class=\"cell-sub\">Booked by " + (l.booking.created_by === "assistant" ? "the assistant" : "staff") + "</div></div>" +
        (rev && rev.created_by === "assistant" && rev.review_status === "pending" ? '<p class="notice notice-info">Not reviewed yet.</p><div class="actions"><button class="btn btn-primary" type="button" data-action="review">Review booking</button></div>' : "") + "</div>");
    }
    if (conv) {
      h.push('<div class="panel-section"><h3>AI call summary</h3><ul class="summary">' + conv.summary.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div>");
      var cap = conv.captured || {};
      h.push('<div class="panel-section"><h3>Answers captured</h3><dl class="facts"><dt>Treatment</dt><dd>' + esc(cap.treatment) +
        "</dd><dt>Preferred slot</dt><dd>" + esc(cap.slot) + "</dd><dt>Urgency</dt><dd>" + esc(cap.urgency) + "</dd></dl></div>");
      h.push('<div class="panel-section"><h3>Transcript (last turns)</h3><div class="transcript">' + conv.transcript.map(function (t) {
        return '<div class="line line-' + (t.who === "Caller" ? "caller" : "assistant") + '"><span class="line-who">' + esc(t.who) + "</span>" + esc(t.text) + "</div>";
      }).join("") + '</div><p class="proto-note">Recording playback arrives with the telephony provider.</p></div>');
    }
    if (a.messages && a.messages.length) {
      h.push('<div class="panel-section"><h3>WhatsApp</h3><ul class="msg-list">' + a.messages.map(function (m) {
        var head = m.direction === "inbound" ? "Patient replied" : (TEMPLATE_NAMES[m.template] || m.template) + " · " + (MSG_STATUS[m.status] || m.status);
        var when = m.status === "queued" && m.due_at ? "due " + dayTime(m.due_at) : clock(m.at);
        return '<li class="msg' + (m.direction === "inbound" ? " msg-in" : "") + '"><span class="line-who">' + esc(head) + " · " + esc(when) +
          "</span>" + esc(m.body) + "</li>";
      }).join("") + "</ul></div>");
    }
    if (l.attempt_log.length) {
      h.push('<div class="panel-section"><h3>Calls</h3><ul class="timeline">' + l.attempt_log.map(function (x) {
        return "<li><span>Call " + x.no + ": " + esc((x.outcome || "in progress").replace("_", " ")) + " · " + esc(x.by) + '</span><span class="when">' + clock(x.at) + "</span></li>";
      }).join("") + "</ul></div>");
    }
    if (open) {
      var claimNote = l.claimed_by && !l.claimed_by_me ? '<p class="notice notice-warn">' + esc(l.claimed_by) + " is calling this lead.</p>" : "";
      h.push('<div class="panel-section"><h3>Call</h3>' + claimNote + '<div class="actions"><a class="btn btn-primary" href="' + esc(tel) +
        '" data-action="claim">Call ' + esc(l.phone) + "</a></div></div>");
      h.push('<div class="panel-section"><h3>What happened?</h3><div class="outcome-grid">' +
        '<button class="btn btn-primary" type="button" data-action="book">Reached: book consultation</button>' +
        '<button class="btn" type="button" data-action="follow_up">Reached: follow up later</button>' +
        '<button class="btn" type="button" data-action="no_answer">No answer</button>' +
        '<button class="btn" type="button" data-action="not_interested">Reached: not interested</button>' +
        '<button class="btn btn-danger-quiet wide" type="button" data-action="invalid">Wrong or invalid number</button></div></div>');
    }
    if (ho) {
      var fb = state.feedback && state.feedback[ho.id];
      h.push('<div class="panel-section"><h3>Was this handover right?</h3><div class="feedback-row">' +
        '<button class="btn icon-btn" type="button" data-action="fb-up" aria-pressed="' + (fb && fb.ok === true) + '" aria-label="Yes, the handover was right">Yes</button>' +
        '<button class="btn icon-btn" type="button" data-action="fb-down" aria-pressed="' + (fb && fb.ok === false) + '" aria-label="No, the handover was not right">No</button>' +
        (fb ? '<span class="cell-sub">Thanks. This goes into the weekly review.</span>' : "") + "</div>" +
        (fb && fb.ok === false ? '<div class="reason-chips" role="group" aria-label="What was wrong?">' + FEEDBACK_REASONS.map(function (r) {
          return '<button class="btn btn-sm" type="button" data-action="fb-reason" data-reason="' + esc(r) + '" aria-pressed="' + (fb.reason === r) + '">' + esc(r) + "</button>";
        }).join("") + "</div>" : "") + "</div>");
    }
    p.innerHTML = h.join("");
    paintSla();
  }

  state.feedback = {};
  function sendFeedback(ho, ok, reason) {
    state.feedback[ho.id] = { ok: ok, reason: reason || null }; renderPanel();
    api("/v1/handovers/" + ho.id + "/feedback", { method: "POST", body: { is_correct: ok, reason: reason || null } }).catch(showError);
  }

  $("panel").addEventListener("click", function (e) {
    var b = e.target.closest("[data-action]"); if (!b || !state.detail) return;
    var l = state.detail, a = b.dataset.action, ho = l.assistant && l.assistant.handover;
    if (a === "close") { state.selected = null; state.detail = null; renderList(); renderPanel(); return; }
    if (a === "claim") { api("/v1/leads/" + l.id + "/claim", { method: "POST" }).then(refresh).catch(showError); return; }  // tel: link still opens
    if (a === "book") { openBook(); return; }
    if (a === "review") { openReview(l.assistant.booking_review.booking_id); return; }
    if (a === "follow_up") { $("note-text").value = ""; $("note-dialog").showModal(); return; }
    if (a === "fb-up") { sendFeedback(ho, true); return; }
    if (a === "fb-down") { sendFeedback(ho, false); return; }
    if (a === "fb-reason") { sendFeedback(ho, false, b.dataset.reason); return; }
    var outcome = { no_answer: "no_answer", not_interested: "reached_not_interested", invalid: "invalid_number" }[a];
    if (outcome) recordOutcome(outcome, null);
  });

  function recordOutcome(outcome, note) {
    var name = state.detail.name;
    return api("/v1/leads/" + state.detail.id + "/outcome", { method: "POST", body: { outcome: outcome, note: note } })
      .then(function () { toast("Saved for " + name + "."); return refresh(); }).catch(showError);
  }
  $("note-save").addEventListener("click", function () { $("note-dialog").close(); recordOutcome("reached_follow_up", $("note-text").value.trim()); });

  // ---------------------------------------------------------------- slots: shared picker
  function slotPicker(container, clinicId, name, onLoaded) {
    container.innerHTML = '<p class="hint">Loading slots...</p>';
    return api("/v1/slots?clinic=" + encodeURIComponent(clinicId)).then(function (r) {
      if (onLoaded) onLoaded(r);
      if (!r.slots.length) { container.innerHTML = '<p class="hint">No open slots in the next 7 days. Add slots first.</p>'; return; }
      var lastDay = "", html = '<legend class="visually-hidden">Choose a slot</legend>';
      r.slots.forEach(function (s, i) {
        var day = new Date(s.start_at).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "long", day: "numeric", month: "short" });
        if (day !== lastDay) { html += '<div class="slot-day">' + esc(day) + "</div>"; lastDay = day; }
        html += '<label class="slot"><input type="radio" name="' + name + '" value="' + esc(s.id) + '"' + (i === 0 ? " checked" : "") + "><span><strong>" +
          esc(clock(s.start_at)) + "</strong> · " + esc(s.dentist) + "</span></label>";
      });
      container.innerHTML = html;
    }).catch(showError);
  }

  function openBook() {
    var l = state.detail;
    $("book-sub").textContent = l.name + " · " + TREATMENT[l.treatment] + " · " + l.clinic;
    $("book-error").hidden = true;
    $("book-dialog").showModal();
    slotPicker($("book-slots"), l.clinic_id, "slot", function (r) {
      $("book-stale").hidden = !r.stale;
      $("book-stale").textContent = r.refreshed_at ? "The slot list was last updated " + ago(r.refreshed_at) + ". Check the calendar before booking."
        : "The slot list has never been updated for this clinic.";
    });
  }
  $("book-confirm").addEventListener("click", function () {
    var picked = $("book-form").querySelector('input[name="slot"]:checked'); if (!picked) return;
    var name = state.detail.name;
    api("/v1/leads/" + state.detail.id + "/bookings", { method: "POST", body: { slot_id: picked.value } })
      .then(function (r) { $("book-dialog").close(); toast("Booked " + name + " for " + dayTime(r.start_at) + "."); refresh(); })
      .catch(function (e) { $("book-error").textContent = e.message; $("book-error").hidden = false; if (e.status === 409) openBook(); });
  });

  // ---------------------------------------------------------------- booking review
  function openReview(bookingId) {
    var l = state.detail, body = $("review-body");
    var b = state.booked.filter(function (x) { return x.booking_id === bookingId; })[0];
    body.innerHTML = '<h2 id="review-title">Review booking</h2><p class="dialog-sub">' + esc(l ? l.name : "") + " · booked by the assistant</p>" +
      (b ? '<div class="booking-card"><div class="booking-slot">' + esc(dayTime(b.start_at)) + "</div><div>" + esc(b.dentist) + " · " + esc(b.clinic) +
        '</div><div class="cell-sub">Enquiry: ' + esc(TREATMENT[b.treatment]) + "</div></div>" : "") +
      '<p class="dialog-sub">Check the slot, dentist and treatment match what the patient asked for. Read the transcript in the side panel.</p>' +
      '<p class="error" id="review-error" hidden></p>' +
      '<div class="dialog-actions"><button class="btn" type="button" data-r="close">Close</button>' +
      '<button class="btn btn-danger-quiet" type="button" data-r="cancel">Cancel booking</button>' +
      '<button class="btn" type="button" data-r="change">Change time</button>' +
      '<button class="btn btn-primary" type="button" data-r="approve">Approve</button></div>';
    body.dataset.booking = bookingId;
    if (!$("review-dialog").open) $("review-dialog").showModal();
  }
  function reviewAction(body, payload, okMsg) {
    api("/v1/bookings/" + body.dataset.booking + "/review", { method: "POST", body: payload })
      .then(function () { $("review-dialog").close(); toast(okMsg); refresh(); })
      .catch(function (e) { var er = $("review-error"); if (er) { er.textContent = e.message; er.hidden = false; } else showError(e); });
  }
  $("review-body").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-r]"); if (!btn) return;
    var body = this, r = btn.dataset.r;
    if (r === "close") { $("review-dialog").close(); return; }
    if (r === "approve") { reviewAction(body, { action: "approve" }, "Booking approved."); return; }
    if (r === "change") {
      body.innerHTML = '<h2 id="review-title">Change time</h2><p class="dialog-sub">Pick the new slot. Tell the patient when you call.</p>' +
        '<fieldset class="slots slot-scroll" id="review-slots"></fieldset><p class="error" id="review-error" hidden></p>' +
        '<div class="dialog-actions"><button class="btn" type="button" data-r="close">Back out</button><button class="btn btn-primary" type="button" data-r="change-confirm">Change booking</button></div>';
      slotPicker($("review-slots"), state.detail.clinic_id, "newslot");
      return;
    }
    if (r === "change-confirm") {
      var p = body.querySelector('input[name="newslot"]:checked'); if (!p) return;
      reviewAction(body, { action: "change", slot_id: p.value }, "Booking moved."); return;
    }
    if (r === "cancel") {
      body.innerHTML = '<h2 id="review-title">Cancel booking</h2><p class="dialog-sub">The lead goes back to Needs you so someone calls the patient.</p>' +
        '<label class="label" for="cancel-reason">Reason</label><select class="select" id="cancel-reason"><option value="">Choose a reason</option>' +
        "<option>Wrong treatment or dentist</option><option>Slot no longer available</option><option>Patient needs a different clinic</option><option>Duplicate booking</option></select>" +
        '<p class="error" id="review-error" hidden></p>' +
        '<div class="dialog-actions"><button class="btn" type="button" data-r="close">Keep booking</button><button class="btn btn-primary" type="button" data-r="cancel-confirm">Cancel booking</button></div>';
      return;
    }
    if (r === "cancel-confirm") {
      var reason = $("cancel-reason").value;
      if (!reason) { $("review-error").textContent = "Choose a reason to cancel."; $("review-error").hidden = false; return; }
      reviewAction(body, { action: "cancel", reason: reason }, "Booking cancelled. The lead is back in Needs you.");
    }
  });

  // ---------------------------------------------------------------- slots maintenance
  $("slots-btn").addEventListener("click", function () {
    var c = $("s-clinic"); c.innerHTML = "";
    state.me.clinics.forEach(function (x) { c.appendChild(new Option(x.name, x.id)); });
    if (state.clinic !== "all") c.value = state.clinic;
    $("s-day").value = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    $("slots-error").hidden = true; loadDentists(); $("slots-dialog").showModal();
  });
  function loadDentists() {
    var clinic = $("s-clinic").value;
    api("/v1/dentists?clinic=" + encodeURIComponent(clinic)).then(function (r) {
      var s = $("s-dentist"); s.innerHTML = "";
      r.dentists.forEach(function (d) { s.appendChild(new Option(d.name, d.id)); });
    }).catch(showError);
    api("/v1/slots?clinic=" + encodeURIComponent(clinic)).then(function (r) {
      $("s-refreshed").textContent = r.refreshed_at ? "Last updated " + ago(r.refreshed_at) + ". " + r.slots.length + " open slots in the next 7 days." : "Never updated.";
    }).catch(function () {});
  }
  $("s-clinic").addEventListener("change", loadDentists);
  $("slots-save").addEventListener("click", function () {
    var body = { clinic_id: $("s-clinic").value, dentist_id: $("s-dentist").value, day: $("s-day").value,
      start: $("s-start").value, end: $("s-end").value, duration_min: +$("s-duration").value };
    api("/v1/slots/bulk", { method: "POST", body: body })
      .then(function (r) { toast(r.created + " slots added."); loadDentists(); })
      .catch(function (e) { $("slots-error").textContent = e.message; $("slots-error").hidden = false; });
  });

  // ---------------------------------------------------------------- test calls
  var tc = { id: null, busy: false };
  function tcLine(who, text) {
    var d = document.createElement("div");
    d.className = "tc-line tc-" + who.toLowerCase();
    if (who === "System") { d.textContent = text; } else {
      var w = document.createElement("span"); w.className = "line-who"; w.textContent = who === "Assistant" ? "Assistant" : "You (caller)";
      d.appendChild(w); d.appendChild(document.createTextNode(text));
    }
    $("tc-log").appendChild(d); $("tc-log").scrollTop = $("tc-log").scrollHeight;
  }
  function tcReset() {
    tc.id = null; $("tc-log").innerHTML = ""; $("tc-log").hidden = true; $("tc-input").hidden = true; $("tc-result").hidden = true;
    $("tc-setup").hidden = false; $("tc-start").hidden = false;
  }
  $("testcall-btn").addEventListener("click", function () {
    var c = $("tc-clinic"); c.innerHTML = "";
    state.me.clinics.forEach(function (x) { c.appendChild(new Option(x.name, x.id)); });
    tcReset(); $("tc-dialog").showModal();
  });
  $("tc-close").addEventListener("click", function () { $("tc-dialog").close(); });
  $("tc-start").addEventListener("click", function () {
    $("tc-log").innerHTML = ""; $("tc-result").hidden = true;
    api("/v1/test-calls", { method: "POST", body: { name: $("tc-name").value, treatment: $("tc-treatment").value,
      clinic_id: $("tc-clinic").value, language: $("tc-lang").value } })
      .then(function (r) {
        tc.id = r.id; $("tc-setup").hidden = true; $("tc-start").hidden = true; $("tc-log").hidden = false; $("tc-input").hidden = false;
        tcLine("Assistant", r.say); $("tc-text").focus();
      }).catch(showError);
  });
  function tcSend(payload, shown) {
    if (!tc.id || tc.busy) return;
    tc.busy = true;
    if (shown) tcLine(shown[0], shown[1]);
    api("/v1/test-calls/" + tc.id + "/turn", { method: "POST", body: payload }).then(function (r) {
      if (r.say) tcLine("Assistant", r.say);
      (r.guard_events || []).forEach(function (g) {
        if (g.type === "triggers") tcLine("System", "Guardrail: " + g.triggers.join(", "));
      });
      if (r.end) {
        $("tc-input").hidden = true;
        var res = "Call ended: " + (r.outcome || "ended") +
          (r.handover ? " · handover: " + ((TAGS[r.handover.reason] || [r.handover.reason])[0]) + (r.handover.urgency === "urgent" ? " (urgent)" : "") : "") +
          (r.booking ? " · booked " + dayTime(r.booking.start_at) + " with " + r.booking.dentist + " (practice only, not saved)" : "");
        if (r.summary) res += " · Summary: " + r.summary.lines.join(" ");
        $("tc-result").textContent = res; $("tc-result").hidden = false; $("tc-start").hidden = false; $("tc-start").textContent = "New test call";
        $("tc-setup").hidden = false;
      }
    }).catch(showError).then(function () { tc.busy = false; });
  }
  $("tc-input").addEventListener("submit", function (e) {
    e.preventDefault();
    var t = $("tc-text").value.trim(); if (!t) return;
    $("tc-text").value = ""; tcSend({ text: t }, ["Caller", t]);
  });
  $("tc-silence").addEventListener("click", function () { tcSend({ silence: true }, ["System", "(caller stays silent)"]); });
  $("tc-hangup").addEventListener("click", function () { tcSend({ hangup: true }, ["System", "(caller hangs up)"]); });

  // ---------------------------------------------------------------- ops (managers, admins)
  function fmtPct(x) { return x == null ? "–" : Math.round(x * 100) + "%"; }
  function fmtNum(x, unit) { return x == null ? "–" : Math.round(x) + (unit || ""); }
  function loadOps() {
    var q = "clinic=" + encodeURIComponent(state.clinic);
    return Promise.all([api("/v1/admin/ops?" + q), api("/v1/admin/go-live?" + q), api("/v1/admin/readout?" + q),
      api("/v1/admin/weekly-review?" + q), api("/v1/admin/rules-changes"), api("/v1/admin/rollout")])
      .then(function (r) { renderOps(r[0], r[1]); renderPhase5(r[2], r[3], r[4]); renderRollout(r[5]); }).catch(showError);
  }

  // Phase 6: rollout waves, onboarding, calendars
  function renderRollout(ro) {
    var admin = state.me.role === "admin", h = [];
    h.push('<div class="ops-section"><h3>Rollout · latest G4: ' + esc(ro.latest_g4 || "none") + " · max assistant share " +
      Math.round(ro.max_share * 100) + "% (" + Math.round(ro.permanent_control_share * 100) + "% always on standard callback)" +
      (ro.enforced ? "" : ' <span class="meta">(gates reported only in development)</span>') + '</h3><ul class="check-list">' +
      ro.clinics.map(function (c) {
        var status = c.active ? '<span class="tag tag-ok">active · ' + Math.round((c.share || 0) * 100) + "%</span>" : '<span class="tag">not started</span>';
        var cal = c.active ? ' <span class="meta">calendar: ' + esc(c.calendar) + (c.calendar === "http" ? (c.calendar_synced_at ? ", synced " + esc(clock(c.calendar_synced_at)) : ", never synced") : "") + "</span>" : "";
        var onboard = c.onboarding ? c.onboarding.map(function (o) {
          return o.ok ? "" : (o.attestation && admin ? '<button class="btn btn-sm" type="button" data-onboard="' + esc(o.id) + '" data-clinic="' + esc(c.id) + '">Sign off: ' + esc(o.label) + "</button>"
            : '<span class="tag tag-warn">' + esc(o.label) + "</span>");
        }).join(" ") : "";
        var sync = c.active && c.calendar === "http" ? '<button class="btn btn-sm" type="button" data-sync="' + esc(c.id) + '">Sync now</button>' : "";
        return "<li><span><strong>Wave " + esc(c.wave) + "</strong> · " + esc(c.name) + " " + status + cal + (onboard ? "<br>" + onboard : "") +
          "</span><span>" + sync + "</span></li>";
      }).join("") + "</ul>");
    Object.keys(ro.waves).forEach(function (w) {
      var checks = ro.waves[w], ok = checks.every(function (c) { return c.ok; });
      var anyInactive = ro.clinics.some(function (c) { return String(c.wave) === w && !c.active; });
      if (!anyInactive) return;
      h.push('<p class="cell-sub"><strong>Wave ' + esc(w) + ":</strong> " + checks.map(function (c) { return (c.ok ? "Met: " : "Not met: ") + esc(c.label); }).join(" · ") +
        (admin ? ' <button class="btn btn-sm' + (ok ? " btn-primary" : "") + '" type="button" data-wave="' + esc(w) + '">Start wave ' + esc(w) + "</button>" : "") + "</p>");
    });
    h.push("</div>");
    $("ops-body").insertAdjacentHTML("beforeend", h.join(""));
  }

  // Phase 5: ramp controls, readout + G4, weekly review, change log
  var DECISION_LABEL = { scale: "Scale", extend: "Extend", fix_first: "Fix first", stop_or_redesign: "Stop or redesign" };
  function pctS(x) { return x == null ? "–" : (x * 100).toFixed(1) + "%"; }
  function diffS(d) { return d.diff == null ? "–" : (d.diff >= 0 ? "+" : "") + (d.diff * 100).toFixed(1) + " pts (95% CI " + (d.lo * 100).toFixed(1) + " to " + (d.hi * 100).toFixed(1) + ")"; }
  function renderPhase5(r, wk, ch) {
    var h = [], admin = state.me.role === "admin", p = r.primary, a = r.attendance, sp = r.speed, s = r.safety;
    h.push('<div class="ops-section"><h3>Pilot readout · ' + esc(r.period.from) + " to " + esc(r.period.to) + "</h3>" +
      '<p class="notice notice-' + (r.recommendation.decision === "scale" ? "ok" : r.recommendation.decision === "extend" ? "info" : "warn") +
      '"><strong>Recommendation (G4): ' + esc(r.recommendation.label) + "</strong><br>" + r.recommendation.reasons.map(esc).join("<br>") + "</p>" +
      '<table class="readout-table"><thead><tr><th></th><th>Assistant</th><th>Standard callback</th><th>Difference</th></tr></thead><tbody>' +
      "<tr><td>Booked within 7 days</td><td>" + p.assistant.k + "/" + p.assistant.n + " = " + pctS(p.assistant.rate) + "</td><td>" + p.control.k + "/" + p.control.n +
      " = " + pctS(p.control.rate) + "</td><td>" + esc(diffS(p.diff)) + "</td></tr>" +
      "<tr><td>Attended</td><td>" + a.assistant.attended + "/" + a.assistant.recorded + " = " + pctS(a.assistant.rate) + "</td><td>" + a.control.attended + "/" +
      a.control.recorded + " = " + pctS(a.control.rate) + "</td><td>" + esc(diffS(a.diff)) + "</td></tr>" +
      "<tr><td>Reached within 5 min</td><td>" + pctS(sp.assistant.within_5_min) + "</td><td>" + pctS(sp.control.within_5_min) + "</td><td></td></tr>" +
      "</tbody></table><p class=\"cell-sub\">Handover SLA " + pctS(s.sla_hit_rate) + " · urgent missed " + s.urgent_missed + " · review rejections " +
      pctS(s.review_rejection_rate) + " · thumbs-down " + pctS(s.thumbs_down_rate) + " · " + r.leads.matured + " of " + r.leads.total + " leads have a full 7-day window</p>" +
      '<p class="actions"><a class="btn btn-sm" href="/v1/admin/readout.md?clinic=' + encodeURIComponent(state.clinic) + '">Download full readout (.md)</a>' +
      (admin ? '<button class="btn btn-sm btn-primary" type="button" data-decide="1">Record G4 decision</button>' : "") + "</p>" +
      (r.decisions.length ? '<ul class="check-list">' + r.decisions.map(function (d) {
        return "<li><span><strong>" + esc(DECISION_LABEL[d.decision]) + "</strong> (recommended: " + esc(DECISION_LABEL[d.recommended]) + ") · " + esc(d.notes) +
          '</span><span class="meta">' + esc(d.by) + ", " + esc(dayTime(d.at)) + "</span></li>";
      }).join("") + "</ul>" : "") + "</div>");
    if (admin) {
      h.push('<div class="ops-section"><h3>Assistant share (gates enforced in staging/production)</h3><ul class="check-list">' +
        Array.prototype.map.call(document.querySelectorAll("#ops-body [data-ks='stop_assistant']"), function (b) {
          var c = b.dataset.clinic;
          return "<li><span>" + esc(c) + '</span><span class="actions">' + ["0", "0.2", "0.5"].map(function (v) {
            return '<button class="btn btn-sm" type="button" data-share="' + v + '" data-clinic="' + esc(c) + '">' + (v * 100) + "%</button>";
          }).join("") + "</span></li>";
        }).join("") + "</ul></div>");
    }
    h.push('<div class="ops-section"><h3>Weekly review · ' + esc(wk.period.from) + " to " + esc(wk.period.to) + "</h3>" +
      '<p class="cell-sub">' + wk.calls_reviewed + " calls reviewed · checklist failures: " + (Object.keys(wk.checklist_failures).map(function (k) { return k + " " + wk.checklist_failures[k]; }).join(", ") || "none") +
      " · thumbs-down: " + wk.thumbs_down.length + "</p>" +
      (Object.keys(wk.thumbs_down_reasons).length ? '<ul class="check-list">' + Object.keys(wk.thumbs_down_reasons).map(function (k) {
        return "<li><span>" + esc(k) + "</span><span>" + wk.thumbs_down_reasons[k] + "</span></li>"; }).join("") + "</ul>" : "") +
      '<p class="cell-sub">Handover mix: ' + (wk.handover_mix.slice(0, 8).map(function (m) { return esc(m.reason) + " (" + esc(m.language) + ") " + m.count; }).join(" · ") || "none") + "</p></div>");
    h.push('<div class="ops-section"><h3>Rules change log · running ' + esc(ch.current_version) + "</h3>" +
      '<p class="actions"><button class="btn btn-sm" type="button" data-change="1">Log a change</button></p>' +
      (ch.changes.length ? '<ul class="check-list">' + ch.changes.slice(0, 10).map(function (c) {
        return "<li><span><strong>" + esc(c.version) + "</strong> · " + esc(c.area) + ": " + esc(c.description) + '</span><span class="meta">' + esc(c.by || "") + ", " + esc(dayTime(c.at)) + "</span></li>";
      }).join("") + "</ul>" : '<p class="hint">No changes logged yet.</p>') + "</div>");
    $("ops-body").insertAdjacentHTML("beforeend", h.join(""));
  }

  function renderOps(o, gl) {
    var m = o.metrics, h = [];
    var tiles = [
      ["First dial p90", fmtNum(m.first_dial_seconds.p90, " s"), "Target 60 s · " + m.first_dial_seconds.count + " calls today"],
      ["Handover SLA", fmtPct(m.handovers.sla_hit_rate), m.handovers.on_time + " of " + m.handovers.decided + " on time · G3 needs 80%"],
      ["Urgent missed", m.handovers.urgent_missed, "Today; any miss stops the assistant at 2× SLA"],
      ["Review rejections", fmtPct(m.booking_review.rejection_rate), m.booking_review.cancelled + " of " + m.booking_review.reviewed + " · pause at 15%"],
      ["WhatsApp failed", m.whatsapp.failed, m.whatsapp.sent + " sent today"],
      ["Groq p90 first token", fmtNum(m.llm.ttft_p90_ms, " ms"), m.llm.enabled ? m.llm.calls_last_hour + " calls/h · " + m.llm.rate_limited + " rate-limited" : "Not configured: rules only"],
      ["Breakers", Object.keys(m.breakers).filter(function (k) { return m.breakers[k]; }).join(", ") || "All closed", "Telephony, LLM"],
      ["Voice agent", m.voice_agent_enabled ? "Enabled" : "Off", "VOICE_AGENT_ENABLED"]
    ];
    h.push('<div class="ops-grid">' + tiles.map(function (t) {
      return '<div class="stat"><div class="stat-label">' + esc(t[0]) + '</div><div class="stat-value">' + esc(t[1]) + '</div><div class="stat-sub">' + esc(t[2]) + "</div></div>";
    }).join("") + "</div>");
    h.push('<div class="ops-section"><h3>Open alerts</h3>' + (o.alerts.length ? o.alerts.map(function (a) {
      return '<div class="alert-row alert-' + a.severity + '"><strong>' + esc(a.severity) + "</strong> · " + esc(a.clinic_id || "all clinics") + ": " + esc(a.message) + "</div>";
    }).join("") : '<p class="hint">None.</p>') + "</div>");
    h.push('<div class="ops-section"><h3>Clinics and kill switch</h3><ul class="check-list">' + m.clinics.map(function (c) {
      return "<li><span><strong>" + esc(c.clinic_id) + "</strong> · assistant share " + Math.round(c.share * 100) + "%" +
        (c.booking_paused ? ' · <span class="tag tag-warn">AI booking paused</span>' : "") +
        (c.live_since ? ' <span class="meta">live since ' + esc(dayTime(c.live_since)) + "</span>" : "") + "</span><span class=\"actions\">" +
        '<button class="btn btn-sm btn-danger-quiet" type="button" data-ks="stop_assistant" data-clinic="' + esc(c.clinic_id) + '">Stop assistant</button>' +
        (c.booking_paused ? '<button class="btn btn-sm" type="button" data-ks="resume_booking" data-clinic="' + esc(c.clinic_id) + '">Resume booking</button>'
          : '<button class="btn btn-sm" type="button" data-ks="pause_booking" data-clinic="' + esc(c.clinic_id) + '">Pause AI booking</button>') + "</span></li>";
    }).join("") + '</ul><p class="actions"><button class="btn btn-sm" type="button" data-ks="drill">Record kill-switch drill</button></p></div>');
    h.push('<div class="ops-section"><h3>Gate G2: go-live ' + (gl.g2_passed ? '<span class="tag tag-ok">passed</span>' : '<span class="tag tag-warn">not passed</span>') +
      (gl.enforced ? "" : ' <span class="meta">(reported only in development)</span>') + '</h3><ul class="check-list">' + gl.g2.map(function (c) {
        var right = c.ok ? '<span class="tag tag-ok">' + (c.by ? "Signed: " + esc(c.by) : "OK") + "</span>"
          : c.attestation && state.me.role === "admin" ? '<button class="btn btn-sm" type="button" data-attest="' + esc(c.id) + '">Sign off</button>'
          : '<span class="tag tag-warn">Missing</span>';
        return "<li><span>" + esc(c.label) + "</span>" + right + "</li>";
      }).join("") + "</ul></div>");
    h.push('<div class="ops-section"><h3>Gate G3: ramp to 50%</h3><ul class="check-list">' + Object.keys(gl.g3).map(function (cid) {
      var checks = gl.g3[cid], ok = checks.every(function (c) { return c.ok; });
      return "<li><span><strong>" + esc(cid) + "</strong> · " + checks.map(function (c) { return (c.ok ? "Met: " : "Not met: ") + esc(c.label); }).join(" · ") + "</span>" +
        (ok ? '<span class="tag tag-ok">passed</span>' : '<span class="tag tag-warn">not yet</span>') + "</li>";
    }).join("") + "</ul></div>");
    $("ops-body").innerHTML = h.join("");
  }
  $("ops-btn").addEventListener("click", function () { $("ops-body").innerHTML = '<p class="hint">Loading...</p>'; $("ops-dialog").showModal(); loadOps(); });
  $("ops-close").addEventListener("click", function () { $("ops-dialog").close(); });
  $("ops-body").addEventListener("click", function (e) {
    var wv = e.target.closest("[data-wave]"), ob = e.target.closest("[data-onboard]"), sy = e.target.closest("[data-sync]");
    if (wv) {
      if (!window.confirm("Start wave " + wv.dataset.wave + "? Its clinics join at 0% and ramp like the pilot did.")) return;
      api("/v1/admin/rollout/waves/" + wv.dataset.wave + "/activate", { method: "POST" })
        .then(function (r) { toast("Activated: " + r.activated.join(", ")); loadOps(); }).catch(showError);
      return;
    }
    if (ob) {
      var note = window.prompt("Sign off '" + ob.textContent.replace("Sign off: ", "") + "' for " + ob.dataset.clinic + ". What did you check?");
      if (!note) return;
      api("/v1/admin/rollout/onboarding", { method: "POST", body: { clinic_id: ob.dataset.clinic, item: ob.dataset.onboard, note: note } })
        .then(loadOps).catch(showError);
      return;
    }
    if (sy) {
      api("/v1/admin/clinics/" + sy.dataset.sync + "/calendar/sync", { method: "POST" })
        .then(function (r) { toast("Synced: " + r.remote + " slots, " + r.blocked + " blocked."); loadOps(); }).catch(showError);
      return;
    }
    var sh = e.target.closest("[data-share]"), dc = e.target.closest("[data-decide]"), cg = e.target.closest("[data-change]");
    if (sh) {
      if (!window.confirm("Set the assistant share for " + sh.dataset.clinic + " to " + (sh.dataset.share * 100) + "%? Only new leads are affected.")) return;
      api("/v1/admin/experiment/" + encodeURIComponent(sh.dataset.clinic), { method: "PUT", body: { assistant_share: +sh.dataset.share } })
        .then(function () { toast("Share updated."); loadOps(); }).catch(showError);
      return;
    }
    if (dc) {
      var d = window.prompt("Record the G4 decision: scale, extend, fix_first or stop_or_redesign");
      if (!d) return;
      var notes = window.prompt("Why? (recorded with your name and a snapshot of this readout)");
      if (!notes) return;
      api("/v1/admin/readout/decision", { method: "POST", body: { decision: d.trim(), notes: notes } })
        .then(function () { toast("G4 decision recorded."); loadOps(); }).catch(showError);
      return;
    }
    if (cg) {
      var version = window.prompt("Rules version this change ships in (e.g. r5.1)");
      if (!version) return;
      var area = window.prompt("Area: lines, keywords, understanding, prompt, thresholds or other", "keywords");
      var desc = area && window.prompt("What changed?");
      if (!desc) return;
      var why = window.prompt("Why? (e.g. thumbs-down pattern, call review finding)") || null;
      api("/v1/admin/rules-changes", { method: "POST", body: { version: version, area: area.trim(), description: desc, reason: why } })
        .then(function () { toast("Change logged."); loadOps(); }).catch(showError);
      return;
    }
    var ks = e.target.closest("[data-ks]"), at = e.target.closest("[data-attest]");
    if (ks) {
      var label = ks.textContent, reason = window.prompt(label + (ks.dataset.clinic ? " for " + ks.dataset.clinic : "") + ". Reason (recorded):");
      if (!reason || reason.trim().length < 3) return;
      api("/v1/admin/kill-switch", { method: "POST", body: { action: ks.dataset.ks, clinic_id: ks.dataset.clinic || null, reason: reason.trim() } })
        .then(function () { toast(label + ": done."); loadOps(); refresh(); }).catch(showError);
    }
    if (at) {
      var note = window.prompt("Sign off: what evidence did you check? (recorded with your name)");
      if (!note) return;
      api("/v1/admin/go-live/attest", { method: "POST", body: { item: at.dataset.attest, note: note } }).then(loadOps).catch(showError);
    }
  });

  // ---------------------------------------------------------------- live transfers (Phase 6)
  function paintTransfer(t) {
    var b = $("transfer-btn");
    b.setAttribute("aria-pressed", t.available);
    b.textContent = t.available ? "Live transfers: on until " + clock(t.until) : "Live transfers: off";
    b.classList.toggle("btn-primary", !!t.available);
  }
  function loadTransfer() { api("/v1/me/transfer").then(paintTransfer).catch(function () {}); }
  $("transfer-btn").addEventListener("click", function () {
    var on = this.getAttribute("aria-pressed") !== "true", body = { available: on };
    if (on) {
      var phone = window.prompt("Callers who ask for a person will be connected to this phone for the next 4 hours. Your mobile number (leave blank to keep the saved one):", "");
      if (phone === null) return;
      if (phone.trim()) body.phone = phone.trim();
    }
    api("/v1/me/transfer", { method: "POST", body: body }).then(loadTransfer).catch(showError);
  });

  // ---------------------------------------------------------------- daily call reviews (P5-02)
  var rv = { calls: [], tags: [], current: null, answers: {} };
  function istToday() { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()); }
  function loadReviews() {
    var q = "day=" + $("reviews-day").value + "&clinic=" + encodeURIComponent(state.clinic);
    api("/v1/reviews/sample?" + q).then(function (r) {
      rv.calls = r.calls; rv.tags = r.issue_tags;
      $("reviews-list").innerHTML = r.calls.length ? r.calls.map(function (c) {
        return '<button class="review-item" type="button" data-call="' + esc(c.call_id) + '"' + (rv.current === c.call_id ? ' aria-current="true"' : "") + ">" +
          "<strong>" + esc(c.name) + "</strong> · " + esc(c.clinic) + " · " + esc(LANG[c.language]) +
          '<span class="cell-sub">' + esc(clock(c.started_at)) + " · " + esc(c.outcome || "") + (c.handover ? " · " + esc(c.handover) : "") +
          " · " + (c.reviewed_by_me ? "reviewed by you" : c.reviews ? c.reviews + " review(s)" : "not reviewed") + "</span></button>";
      }).join("") : '<p class="hint">No completed assistant calls on this day.</p>';
    }).catch(showError);
  }
  function triButtons(key, allowNa) {
    var opts = [["true", "Yes"], ["false", "No"]].concat(allowNa ? [["null", "N/A"]] : []);
    return '<span class="tri">' + opts.map(function (o) {
      return '<button class="btn btn-sm" type="button" data-q="' + key + '" data-v="' + o[0] + '" aria-pressed="' + (String(rv.answers[key]) === o[0]) + '">' + o[1] + "</button>";
    }).join("") + "</span>";
  }
  function renderReviewForm(c) {
    var qs = [["disclosure_ok", "Disclosure given in the first sentence", false], ["booking_ok", "Booking correct (slot, clinic, read-back)", true],
      ["handover_ok", "Handover appropriate (reason, urgency, promise)", true], ["tone_ok", "Tone warm, clear and respectful", false]];
    $("review-detail").innerHTML = "<h3>" + esc(c.name) + " · " + esc(c.outcome || "") + " · rules " + esc(c.rules_version || "") + "</h3>" +
      '<div class="transcript">' + c.transcript.map(function (t) {
        return '<div class="line line-' + (t.who === "Caller" ? "caller" : "assistant") + '"><span class="line-who">' + esc(t.who) + "</span>" + esc(t.text) + "</div>";
      }).join("") + "</div>" +
      qs.map(function (q) { return '<div class="review-q"><span>' + esc(q[1]) + "</span>" + triButtons(q[0], q[2]) + "</div>"; }).join("") +
      '<div class="field"><span class="label">Issues</span>' + rv.tags.map(function (t) {
        return '<label class="tag-check"><input type="checkbox" value="' + esc(t) + '">' + esc(t.replace(/_/g, " ")) + "</label>";
      }).join("") + "</div>" +
      '<label class="label" for="review-notes">Notes</label><textarea class="input" id="review-notes" rows="2" maxlength="500"></textarea>' +
      '<p class="actions"><button class="btn btn-primary" type="button" id="review-save">Save review</button></p>';
  }
  $("reviews-btn").addEventListener("click", function () {
    if (!$("reviews-day").value) $("reviews-day").value = istToday();
    $("reviews-dialog").showModal(); loadReviews();
  });
  $("reviews-close").addEventListener("click", function () { $("reviews-dialog").close(); });
  $("reviews-day").addEventListener("change", loadReviews);
  $("reviews-list").addEventListener("click", function (e) {
    var b = e.target.closest("[data-call]"); if (!b) return;
    rv.current = b.dataset.call; rv.answers = {};
    loadReviews();
    api("/v1/reviews/calls/" + rv.current).then(renderReviewForm).catch(showError);
  });
  $("review-detail").addEventListener("click", function (e) {
    var q = e.target.closest("[data-q]");
    if (q) {
      rv.answers[q.dataset.q] = JSON.parse(q.dataset.v);
      q.parentNode.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", b === q); });
      return;
    }
    if (e.target.id === "review-save") {
      if (typeof rv.answers.disclosure_ok !== "boolean" || typeof rv.answers.tone_ok !== "boolean") { toast("Answer the disclosure and tone questions."); return; }
      var tags = Array.prototype.map.call($("review-detail").querySelectorAll(".tag-check input:checked"), function (i) { return i.value; });
      api("/v1/reviews/calls/" + rv.current, { method: "POST", body: { disclosure_ok: rv.answers.disclosure_ok, booking_ok: rv.answers.booking_ok == null ? null : rv.answers.booking_ok,
        handover_ok: rv.answers.handover_ok == null ? null : rv.answers.handover_ok, tone_ok: rv.answers.tone_ok, issue_tags: tags, notes: $("review-notes").value || null } })
        .then(function () { toast("Review saved."); loadReviews(); }).catch(showError);
    }
  });

  // ---------------------------------------------------------------- attendance (P5-04)
  function loadAttendance() {
    api("/v1/attendance?clinic=" + encodeURIComponent(state.clinic)).then(function (r) {
      $("attendance-body").innerHTML = r.appointments.length ? '<ul class="check-list">' + r.appointments.map(function (b) {
        var state_ = b.attended === true ? '<span class="tag tag-ok">Attended</span>' : b.attended === false ? '<span class="tag">No-show</span>' : "";
        return "<li><span><strong>" + esc(b.name) + "</strong> · " + esc(dayTime(b.start_at)) + " · " + esc(b.dentist) + ", " + esc(b.clinic) +
          ' <span class="meta">booked by ' + esc(b.booked_by) + "</span> " + state_ + '</span><span class="actions">' +
          '<button class="btn btn-sm" type="button" data-att="true" data-b="' + esc(b.booking_id) + '">Attended</button>' +
          '<button class="btn btn-sm" type="button" data-att="false" data-b="' + esc(b.booking_id) + '">No-show</button></span></li>';
      }).join("") + "</ul>" : '<p class="hint">No past appointments in the last 7 days.</p>';
    }).catch(showError);
  }
  $("attendance-btn").addEventListener("click", function () { $("attendance-dialog").showModal(); loadAttendance(); });
  $("attendance-close").addEventListener("click", function () { $("attendance-dialog").close(); });
  $("attendance-body").addEventListener("click", function (e) {
    var b = e.target.closest("[data-att]"); if (!b) return;
    api("/v1/bookings/" + b.dataset.b + "/attendance", { method: "POST", body: { attended: b.dataset.att === "true" } })
      .then(loadAttendance).catch(showError);
  });

  // ---------------------------------------------------------------- live clock + timers
  setInterval(function () {
    $("clock").textContent = new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit" }) + " IST";
    document.querySelectorAll("[data-ago]").forEach(function (el) { el.textContent = ago(el.dataset.ago); });
    paintSla();
  }, 1000);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.detail && !document.querySelector("dialog[open]")) { state.selected = null; state.detail = null; renderList(); renderPanel(); }
  });

  // ---------------------------------------------------------------- boot
  api("/v1/auth/me").then(start).catch(function () { showLogin(); });
})();
