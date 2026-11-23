/* Screen 2 — Leads queue. Prototype only: all changes stay in this page. */
(function () {
  "use strict";

  // ---------------------------------------------------------------- constants
  var CLINIC_NAMES = {};
  (window.HS_CLINICS || []).forEach(function (c) { CLINIC_NAMES[c.id] = c.name; });
  var DENTISTS = window.HS_DENTISTS || {};

  var TAGS = {
    asked_person: { label: "Asked for a person", cls: "tag-info" },
    pain_swelling: { label: "Pain or swelling (urgent)", cls: "tag-urgent" },
    price_emi: { label: "Price/EMI question", cls: "tag-warn" },
    clinical: { label: "Clinical question", cls: "tag-primary" },
    couldnt_understand: { label: "Couldn't understand", cls: "" },
    whatsapp_reply: { label: "WhatsApp reply", cls: "tag-ok" }
  };
  var SLA_MIN = { urgent: 5, normal: 15 };
  var WA_STATUS = {
    read: { label: "Read", cls: "tag-ok" }, delivered: { label: "Delivered", cls: "tag-ok" },
    sent: { label: "Sent", cls: "" }, failed: { label: "Not delivered", cls: "tag-urgent" }
  };
  var OUTCOMES = {
    not_called: { label: "Not called yet", cls: "tag-warn" },
    no_answer: { label: "Called, no answer", cls: "" },
    booked: { label: "Reached, booked by staff", cls: "tag-ok" },
    not_interested: { label: "Not interested", cls: "" },
    follow_up: { label: "Reached, follow up Saturday", cls: "tag-info" }
  };
  var TAB_HELP = {
    needs_you: "Handed over by the assistant, or replied on WhatsApp. Urgent first, then longest wait. Target: 5 minutes for urgent, 15 minutes for the rest.",
    booked: "Consultations the assistant booked. Review every booking before the appointment.",
    no_answer: "The assistant could not reach these people. It retries after 5 minutes and 2 hours, then sends a WhatsApp message.",
    standard: "Pilot control group. The assistant does not call these leads. Call them as you normally would and record the outcome."
  };

  var I = {
    phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    up: '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
    down: '<path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/>',
    play: '<polygon points="6 3 20 12 6 21 6 3"/>',
    pause: '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
    check: '<path d="M20 6 9 17l-5-5"/>'
  };
  function icon(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + I[name] + "</svg>";
  }

  // ---------------------------------------------------------------- demo clock
  var base = new Date(); base.setHours(14, 20, 0, 0);
  var loadedAt = Date.now();
  function now() { return base.getTime() + (Date.now() - loadedAt); }
  function ago(min) { return base.getTime() - min * 60000; }

  // ---------------------------------------------------------------- state
  var leads = (window.HS_LEADS || []).map(function (src) {
    var l = JSON.parse(JSON.stringify(src));
    l.enquiredAt = ago(src.enquiredAgo);
    l.firstReachedAt = src.firstReachedAgo == null ? null : ago(src.firstReachedAgo);
    if (src.handoverAgo != null) l.handoverAt = ago(src.handoverAgo);
    if (src.attempts) l.attempts = src.attempts.map(function (a) { return { label: a[0], result: a[1], at: ago(a[2]) }; });
    if (src.nextRetryIn != null) l.nextRetryAt = base.getTime() + src.nextRetryIn * 60000;
    l.urgent = (src.tags || []).indexOf("pain_swelling") >= 0;
    l.claimedAt = null;
    l.feedback = null;
    l.feedbackReason = null;
    return l;
  });

  var state = { tab: "needs_you", clinic: "all", selectedId: null };
  var player = { id: null, pos: 0, playing: false };

  // ---------------------------------------------------------------- helpers
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function clock(ms) {
    var d = new Date(ms), h = d.getHours(), m = d.getMinutes();
    return (h % 12 || 12) + ":" + String(m).padStart(2, "0") + (h >= 12 ? " pm" : " am");
  }
  function mmss(sec) { sec = Math.max(0, Math.floor(sec)); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
  function minsAgo(ms) { var m = Math.max(0, Math.round((now() - ms) / 60000)); return m < 60 ? m + " min ago" : Math.floor(m / 60) + " h " + (m % 60) + " min ago"; }
  function inMins(ms) { var m = Math.max(0, Math.round((ms - now()) / 60000)); return m < 60 ? "in " + m + " min" : "in " + Math.floor(m / 60) + " h " + (m % 60) + " min"; }
  function dayLabel(offset) {
    if (offset === 0) return "Today";
    if (offset === 1) return "Tomorrow";
    var d = new Date(base); d.setDate(d.getDate() + offset);
    return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  }
  function tagHtml(key) { var t = TAGS[key]; return '<span class="tag ' + t.cls + '">' + esc(t.label) + "</span>"; }
  function byId(id) { for (var i = 0; i < leads.length; i++) if (leads[i].id === id) return leads[i]; return null; }
  function visible(l) { return state.clinic === "all" || l.clinic === state.clinic; }
  function inTab(tab) { return leads.filter(function (l) { return visible(l) && l.status === tab; }); }

  function sla(l) {
    var target = l.urgent ? SLA_MIN.urgent : SLA_MIN.normal;
    if (l.claimedAt) {
      return { cls: "sla-claimed", pct: 100, text: "Picked up by you after " + mmss((l.claimedAt - l.handoverAt) / 1000) };
    }
    var waited = (now() - l.handoverAt) / 1000, ratio = waited / (target * 60);
    if (ratio >= 1) return { cls: "sla-over", pct: 100, text: "Over target by " + mmss(waited - target * 60) + " (target " + target + " min)", over: true };
    if (ratio >= 0.7) return { cls: "sla-soon", pct: ratio * 100, text: "Due soon: " + mmss(waited) + " of " + target + " min" };
    return { cls: "sla-ok", pct: ratio * 100, text: mmss(waited) + " of " + target + " min" };
  }
  function slaHtml(l) {
    var s = sla(l);
    return '<div class="sla ' + s.cls + '" data-sla="' + l.id + '"><span class="sla-text">' + esc(s.text) +
      '</span><div class="sla-bar"><div class="sla-fill" style="width:' + s.pct.toFixed(1) + '%"></div></div></div>';
  }
  function updateSla(el, l) {
    var s = sla(l);
    el.className = "sla " + s.cls;
    el.querySelector(".sla-text").textContent = s.text;
    el.querySelector(".sla-fill").style.width = s.pct.toFixed(1) + "%";
  }

  // ---------------------------------------------------------------- strip
  function renderStrip() {
    var all = leads.filter(visible);
    var assistant = all.filter(function (l) { return l.arm === "assistant"; });
    var fast = assistant.filter(function (l) { return l.firstReachedAt != null && l.firstReachedAt - l.enquiredAt <= 5 * 60000; });
    var booked = all.filter(function (l) { return l.status === "booked"; });
    var pending = booked.filter(function (l) { return l.booking.review === "pending"; });
    var waiting = all.filter(function (l) { return l.status === "needs_you"; });
    var over = waiting.filter(function (l) { return sla(l).over; });
    var noAns = all.filter(function (l) { return l.status === "no_answer"; });
    var waSent = noAns.filter(function (l) { return l.nextRetryAt == null; });
    var pct = assistant.length ? Math.round(100 * fast.length / assistant.length) : 0;

    var stats = [
      ["Enquiries received", all.length, "Today, " + (state.clinic === "all" ? "3 pilot clinics" : CLINIC_NAMES[state.clinic])],
      ["Reached within 5 minutes", pct + "%", fast.length + " of " + assistant.length + " assistant-group leads"],
      ["Consults booked by assistant", booked.length, pending.length + " waiting for review"],
      ["Waiting for staff", waiting.length, over.length ? over.length + " over target" : "All within target", over.length > 0],
      ["No answer (retrying)", noAns.length, waSent.length + " sent WhatsApp after 3 calls"]
    ];
    $("strip").innerHTML = stats.map(function (s) {
      return '<div class="stat"><div class="stat-label">' + esc(s[0]) + '</div><div class="stat-value">' + esc(s[1]) +
        '</div><div class="stat-sub' + (s[3] ? " alert" : "") + '">' + esc(s[2]) + "</div></div>";
    }).join("");
  }

  // ---------------------------------------------------------------- tabs
  function renderTabs() {
    document.querySelectorAll('#tabs [role="tab"]').forEach(function (btn) {
      var tab = btn.dataset.tab, sel = tab === state.tab;
      btn.setAttribute("aria-selected", sel ? "true" : "false");
      btn.tabIndex = sel ? 0 : -1;
      btn.querySelector(".count").textContent = inTab(tab).length;
    });
    $("list-pane").setAttribute("aria-labelledby", "tab-" + state.tab);
    $("tab-help").textContent = TAB_HELP[state.tab];
  }

  // ---------------------------------------------------------------- list
  function sorted(tab) {
    var list = inTab(tab);
    if (tab === "needs_you") list.sort(function (a, b) {
      if (!!a.claimedAt !== !!b.claimedAt) return a.claimedAt ? 1 : -1;
      if (a.urgent !== b.urgent) return a.urgent ? -1 : 1;
      return a.handoverAt - b.handoverAt;
    });
    if (tab === "booked") list.sort(function (a, b) {
      var ap = a.booking.review === "pending" ? 0 : 1, bp = b.booking.review === "pending" ? 0 : 1;
      return ap - bp || a.booking.dayOffset - b.booking.dayOffset;
    });
    if (tab === "no_answer") list.sort(function (a, b) {
      return (a.nextRetryAt || Infinity) - (b.nextRetryAt || Infinity);
    });
    if (tab === "standard") list.sort(function (a, b) {
      var ao = a.outcome === "not_called" ? 0 : 1, bo = b.outcome === "not_called" ? 0 : 1;
      return ao - bo || a.enquiredAt - b.enquiredAt;
    });
    return list;
  }

  function leadCell(l) {
    return '<div><button class="name-btn" type="button" data-open="' + l.id + '"><span class="lead-name">' + esc(l.name) + "</span></button>" +
      '<span class="lead-meta">' + esc(l.treatment) + " · " + esc(CLINIC_NAMES[l.clinic]) + " · " + esc(l.language) + "</span></div>";
  }

  var HEADS = {
    needs_you: ["Lead", "Handover reason", "Waiting vs target"],
    booked: ["Lead", "Consultation", "Dentist", "WhatsApp", "Review"],
    no_answer: ["Lead", "Attempts", "Next step"],
    standard: ["Lead", "Enquired", "Outcome"]
  };

  function rowHtml(l, tab) {
    var cells = [leadCell(l)];
    if (tab === "needs_you") {
      cells.push('<div class="cell-tags">' + l.tags.map(tagHtml).join("") + "</div>");
      cells.push(slaHtml(l));
    } else if (tab === "booked") {
      var b = l.booking, wa = WA_STATUS[b.whatsapp];
      cells.push("<div><strong>" + esc(dayLabel(b.dayOffset)) + '</strong><span class="cell-sub">' + esc(b.time) + "</span></div>");
      cells.push("<div>" + esc(b.dentist) + '<span class="cell-sub">' + esc(CLINIC_NAMES[l.clinic]) + "</span></div>");
      cells.push('<div><span class="tag ' + wa.cls + '">' + esc(wa.label) + "</span></div>");
      cells.push(b.review === "pending"
        ? '<div><button class="btn btn-sm" type="button" data-review="' + l.id + '">Review</button></div>'
        : '<div><span class="tag tag-ok">' + (b.review === "changed" ? "Changed" : "Approved") + "</span></div>");
    } else if (tab === "no_answer") {
      var calls = l.attempts.filter(function (a) { return a.label.indexOf("Call") === 0; }).length;
      cells.push("<div><strong>" + calls + " of 3 calls</strong><span class=\"cell-sub\">Last: " + esc(l.attempts[l.attempts.length - 1].result) + "</span></div>");
      cells.push(l.nextRetryAt
        ? '<div>Retry at ' + clock(l.nextRetryAt) + '<span class="cell-sub" data-retry="' + l.id + '">' + inMins(l.nextRetryAt) + "</span></div>"
        : "<div>WhatsApp sent " + clock(l.attempts[l.attempts.length - 1].at) + '<span class="cell-sub">' + esc(l.attempts[l.attempts.length - 1].result) + "</span></div>");
    } else {
      var o = OUTCOMES[l.outcome];
      cells.push("<div>" + clock(l.enquiredAt) + '<span class="cell-sub" data-ago="' + l.id + '">' + minsAgo(l.enquiredAt) + "</span></div>");
      cells.push('<div><span class="tag ' + o.cls + '">' + esc(o.label) + "</span>" +
        (l.claimedAt && l.outcome === "not_called" ? '<span class="cell-sub">Called by you at ' + clock(l.claimedAt) + "</span>" : "") + "</div>");
    }
    var cur = l.id === state.selectedId ? ' aria-current="true"' : "";
    return '<div class="row cols-' + tab + '" data-row="' + l.id + '"' + cur + ">" + cells.join("") + "</div>";
  }

  var EMPTY = {
    needs_you: ["Nothing waiting.", "New handovers from the assistant will appear here."],
    booked: ["No assistant bookings yet today.", "Bookings appear here for review as soon as they are made."],
    no_answer: ["Everyone has been reached.", "Leads the assistant cannot reach will appear here."],
    standard: ["No standard-callback leads.", "Leads randomly assigned to the control group appear here."]
  };

  function renderList() {
    var tab = state.tab, list = sorted(tab);
    if (!list.length) {
      $("list").innerHTML = '<div class="empty"><strong>' + EMPTY[tab][0] + "</strong>" + EMPTY[tab][1] + "</div>";
      return;
    }
    var head = '<div class="row-head cols-' + tab + '">' + HEADS[tab].map(function (h) { return "<span>" + h + "</span>"; }).join("") + "</div>";
    $("list").innerHTML = head + list.map(function (l) { return rowHtml(l, tab); }).join("");
  }

  // ---------------------------------------------------------------- panel
  function renderPanel() {
    var panel = $("panel");
    var l = state.selectedId ? byId(state.selectedId) : null;
    if (!l || !visible(l) || l.status === "closed") {
      state.selectedId = null;
      panel.classList.add("is-empty");
      panel.innerHTML = '<div class="panel-empty">Select a lead to see the call summary, captured answers and actions.</div>';
      return;
    }
    panel.classList.remove("is-empty");
    var h = [];

    // Head
    var armTag = l.arm === "assistant" ? '<span class="tag tag-primary">Assistant group</span>' : '<span class="tag">Standard callback group</span>';
    h.push('<div class="panel-head"><div><h2 id="panel-title">' + esc(l.name) + '</h2><div class="panel-phone">' + esc(l.phone) +
      '</div><div class="panel-badges">' + armTag + '<span class="tag">' + esc(l.language) + "</span>" +
      (l.urgent ? '<span class="tag tag-urgent">Urgent</span>' : "") + "</div></div>" +
      '<button class="btn btn-sm icon-btn panel-close" type="button" data-action="close" aria-label="Close details">' + icon("x") + "</button></div>");

    // Facts
    var reached = l.firstReachedAt
      ? clock(l.firstReachedAt) + " (" + Math.round((l.firstReachedAt - l.enquiredAt) / 60000) + " min after enquiry)"
      : "Not reached by phone";
    h.push('<div class="panel-section"><dl class="facts">' +
      "<dt>Treatment</dt><dd>" + esc(l.treatment) + "</dd>" +
      "<dt>Clinic</dt><dd>" + esc(CLINIC_NAMES[l.clinic]) + "</dd>" +
      "<dt>Language</dt><dd>" + esc(l.language) + "</dd>" +
      "<dt>Enquired</dt><dd>" + clock(l.enquiredAt) + " (" + minsAgo(l.enquiredAt) + ")</dd>" +
      "<dt>First reached</dt><dd>" + esc(reached) + "</dd>" +
      "</dl></div>");

    // Status-specific
    if (l.status === "needs_you") {
      h.push('<div class="panel-section"><h3>Handover</h3><div class="cell-tags" style="margin-bottom:10px">' + l.tags.map(tagHtml).join("") + "</div>" + slaHtml(l) +
        (l.urgent ? '<p class="notice notice-urgent" style="margin:10px 0 0">Patient reports pain or swelling. Call now. The assistant gave safe-care advice and did not book.</p>' : "") +
        (l.whatsappMessage ? '<p class="notice notice-ok" style="margin:10px 0 0"><strong>WhatsApp reply:</strong> “' + esc(l.whatsappMessage) + "”</p>" : "") +
        "</div>");
    }
    if (l.status === "booked") {
      var b = l.booking, wa = WA_STATUS[b.whatsapp];
      h.push('<div class="panel-section"><h3>Booking</h3><div class="booking-card"><div class="booking-slot">' + esc(dayLabel(b.dayOffset)) + ", " + esc(b.time) +
        "</div><div>" + esc(b.dentist) + " · " + esc(CLINIC_NAMES[l.clinic]) + "</div>" +
        '<div style="margin-top:6px">Confirmation sent on WhatsApp: <span class="tag ' + wa.cls + '">' + esc(wa.label) + "</span></div></div>" +
        (b.whatsapp === "failed" ? '<p class="notice notice-warn" style="margin:10px 0 0">WhatsApp could not be delivered. Call to confirm the booking.</p>' : "") +
        (b.review === "pending" ? '<p class="notice notice-info" style="margin:10px 0 0">Booked by the assistant. Not reviewed yet.</p>'
          : '<p class="notice notice-ok" style="margin:10px 0 0">Reviewed: ' + (b.review === "changed" ? "time changed, update sent on WhatsApp." : "approved.") + "</p>") +
        "</div>");
    }
    if (l.attempts && (l.status === "no_answer" || l.status === "needs_you")) {
      h.push('<div class="panel-section"><h3>Contact attempts</h3><ul class="timeline">' +
        l.attempts.map(function (a) { return "<li><span>" + esc(a.label) + ": " + esc(a.result) + '</span><span class="when">' + clock(a.at) + "</span></li>"; }).join("") +
        (l.nextRetryAt ? "<li><span>Next call</span><span class=\"when\">" + clock(l.nextRetryAt) + "</span></li>" : "") +
        "</ul></div>");
    }
    if (l.status === "standard") {
      var o = OUTCOMES[l.outcome];
      h.push('<div class="panel-section"><p class="notice notice-info" style="margin:0 0 10px">Standard callback group (pilot control). The assistant does not call this lead. Call as you normally would and record the outcome, so both groups are measured the same way.</p>' +
        'Outcome: <span class="tag ' + o.cls + '">' + esc(o.label) + "</span>" +
        (l.claimedAt && l.outcome === "not_called" ? ' <span class="cell-sub">Called by you at ' + clock(l.claimedAt) + "</span>" : "") + "</div>");
    }

    // AI summary, captured answers, transcript
    if (l.summary) {
      h.push('<div class="panel-section"><h3>' + (l.recordingSecs ? "AI call summary" : "Summary") + '</h3><ul class="summary">' +
        l.summary.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul></div>");
    }
    if (l.captured) {
      var slotText = l.booking ? dayLabel(l.booking.dayOffset) + ", " + l.booking.time + " (booked)" : l.captured.slot;
      h.push('<div class="panel-section"><h3>Answers captured</h3><dl class="facts">' +
        "<dt>Treatment</dt><dd>" + esc(l.captured.treatment) + "</dd>" +
        "<dt>Preferred slot</dt><dd>" + esc(slotText) + "</dd>" +
        "<dt>Urgency</dt><dd>" + esc(l.captured.urgency) + "</dd></dl></div>");
    }
    if (l.transcript) {
      var playing = player.id === l.id && player.playing, pos = player.id === l.id ? player.pos : 0;
      h.push('<div class="panel-section"><h3>Transcript snippet</h3><div class="transcript">' +
        l.transcript.map(function (t) {
          return '<div class="line line-' + (t[0] === "Caller" ? "caller" : "assistant") + '"><span class="line-who">' + esc(t[0]) + "</span>" + esc(t[1]) + "</div>";
        }).join("") + "</div>" +
        '<div class="player"><button class="btn btn-sm" type="button" data-action="play" aria-pressed="' + playing + '">' + icon(playing ? "pause" : "play") +
        (playing ? "Pause" : "Play recording") + '</button><div class="player-bar"><div class="player-fill" id="player-fill" style="width:' +
        (100 * pos / l.recordingSecs).toFixed(1) + '%"></div></div><span class="player-time" id="player-time">' + mmss(pos) + " / " + mmss(l.recordingSecs) +
        "</span></div><p class=\"proto-note\" style=\"margin-top:6px\">Demo: no audio in the prototype.</p></div>");
    }

    // Actions
    var acts = [];
    if (l.status === "booked") {
      if (l.booking.review === "pending") acts.push('<button class="btn btn-primary" type="button" data-action="review">' + icon("check") + "Review booking</button>");
      acts.push('<button class="btn" type="button" data-action="call">' + icon("phone") + "Call now</button>");
    } else if (!(l.status === "standard" && (l.outcome === "booked" || l.outcome === "not_interested"))) {
      acts.push('<button class="btn btn-primary" type="button" data-action="call">' + icon("phone") + "Call now</button>");
      acts.push('<button class="btn" type="button" data-action="book">' + icon("calendar") + "Book slot</button>");
      if (l.status === "standard" && l.outcome !== "no_answer") acts.push('<button class="btn" type="button" data-action="noanswer">Record no answer</button>');
      acts.push('<button class="btn btn-danger-quiet" type="button" data-action="notinterested">Mark not interested</button>');
    }
    if (acts.length) h.push('<div class="panel-section"><h3>Actions</h3><div class="actions">' + acts.join("") + "</div></div>");

    // Handover feedback
    if (l.status === "needs_you" && l.arm === "assistant") {
      var up = l.feedback === "up", down = l.feedback === "down";
      var reasons = ["Assistant could have handled this", "Should have been urgent", "Wrong reason tag", "Other"];
      h.push('<div class="panel-section"><h3>Was this handover right?</h3><div class="feedback-row">' +
        '<button class="btn icon-btn" type="button" data-action="fb-up" aria-pressed="' + up + '" aria-label="Yes, the handover was right">' + icon("up") + "</button>" +
        '<button class="btn icon-btn" type="button" data-action="fb-down" aria-pressed="' + down + '" aria-label="No, the handover was not right">' + icon("down") + "</button>" +
        (l.feedback ? '<span class="cell-sub">Thanks. This goes into the weekly review.</span>' : "") + "</div>" +
        (down ? '<div class="reason-chips" role="group" aria-label="What was wrong?">' + reasons.map(function (r) {
          return '<button class="btn btn-sm" type="button" data-action="fb-reason" data-reason="' + esc(r) + '" aria-pressed="' + (l.feedbackReason === r) + '">' + esc(r) + "</button>";
        }).join("") + "</div>" : "") + "</div>");
    }

    panel.innerHTML = h.join("");
  }

  function renderAll() { renderStrip(); renderTabs(); renderList(); renderPanel(); }

  function select(id, focusPanel) {
    if (player.id && player.id !== id) stopPlayer();
    state.selectedId = id;
    renderList();
    renderPanel();
    if (focusPanel) $("panel").focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- toasts
  function toast(msg, undo) {
    var el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = "<span>" + esc(msg) + "</span>";
    if (undo) {
      var b = document.createElement("button");
      b.className = "btn btn-link"; b.type = "button"; b.textContent = "Undo";
      b.addEventListener("click", function () { undo(); el.remove(); });
      el.appendChild(b);
    }
    $("toasts").appendChild(el);
    setTimeout(function () { el.remove(); }, undo ? 9000 : 5000);
  }

  // ---------------------------------------------------------------- recording player (simulated)
  var playTimer = null;
  function stopPlayer() { player.playing = false; if (playTimer) { clearInterval(playTimer); playTimer = null; } }
  function togglePlay(l) {
    if (player.id !== l.id) { stopPlayer(); player.id = l.id; player.pos = 0; }
    if (player.playing) { stopPlayer(); renderPanel(); return; }
    if (player.pos >= l.recordingSecs) player.pos = 0;
    player.playing = true;
    playTimer = setInterval(function () {
      player.pos += 1;
      if (player.pos >= l.recordingSecs) { player.pos = l.recordingSecs; stopPlayer(); renderPanel(); return; }
      var fill = $("player-fill"), time = $("player-time");
      if (fill) fill.style.width = (100 * player.pos / l.recordingSecs).toFixed(1) + "%";
      if (time) time.textContent = mmss(player.pos) + " / " + mmss(l.recordingSecs);
    }, 1000);
    renderPanel();
  }

  // ---------------------------------------------------------------- slots + dialogs
  function slotsFor(l) {
    var d = DENTISTS[l.clinic] || ["Dr. On duty"];
    return [
      { day: 0, time: "6:00 pm", dentist: d[0] },
      { day: 1, time: "11:00 am", dentist: d[1] || d[0] },
      { day: 1, time: "5:30 pm", dentist: d[0] },
      { day: 2, time: "10:00 am", dentist: d[1] || d[0] }
    ];
  }
  function slotRadios(l, name) {
    return slotsFor(l).map(function (s, i) {
      return '<label class="slot"><input type="radio" name="' + name + '" value="' + i + '"' + (i === 0 ? " checked" : "") + "><span><strong>" +
        esc(dayLabel(s.day)) + ", " + esc(s.time) + "</strong> · " + esc(s.dentist) + "</span></label>";
    }).join("");
  }

  var bookingFor = null;
  function openBook(l) {
    bookingFor = l;
    $("book-sub").textContent = l.name + " · " + l.treatment + " · " + CLINIC_NAMES[l.clinic];
    $("book-slots").innerHTML = '<legend class="visually-hidden">Choose a slot</legend>' + slotRadios(l, "slot");
    $("book-dialog").showModal();
  }
  $("book-dialog").addEventListener("close", function () {
    var l = bookingFor; bookingFor = null;
    if (!l || $("book-dialog").returnValue !== "confirm") return;
    var picked = $("book-form").querySelector('input[name="slot"]:checked');
    var s = slotsFor(l)[picked ? parseInt(picked.value, 10) : 0];
    var label = dayLabel(s.day) + ", " + s.time + " with " + s.dentist;
    if (l.arm === "control") {
      l.outcome = "booked";
      if (!l.firstReachedAt) l.firstReachedAt = now();
      toast("Booked " + l.name + ": " + label + ". WhatsApp confirmation sent.");
    } else {
      var from = l.status === "needs_you" ? "Needs you" : "No answer";
      l.status = "closed";
      toast("Booked " + l.name + ": " + label + ". WhatsApp confirmation sent. Removed from " + from + ".");
    }
    renderAll();
  });

  function openReview(l) {
    var b = l.booking, body = $("review-body");
    body.innerHTML =
      '<h2 id="review-title">Review booking</h2><p class="dialog-sub">' + esc(l.name) + " · booked by the assistant</p>" +
      '<div class="booking-card" style="margin-bottom:12px"><div class="booking-slot">' + esc(dayLabel(b.dayOffset)) + ", " + esc(b.time) + "</div><div>" +
      esc(b.dentist) + " · " + esc(CLINIC_NAMES[l.clinic]) + "</div><div class=\"cell-sub\">Captured: " + esc(l.captured ? l.captured.treatment : l.treatment) + "</div></div>" +
      "<p class=\"dialog-sub\">Check the slot, dentist and treatment match what the patient asked for.</p>" +
      '<div class="dialog-actions"><button class="btn" type="button" data-r="close">Close</button>' +
      '<button class="btn btn-danger-quiet" type="button" data-r="cancel">Cancel booking</button>' +
      '<button class="btn" type="button" data-r="change">Change time</button>' +
      '<button class="btn btn-primary" type="button" data-r="approve">' + icon("check") + "Approve</button></div>";
    body.dataset.lead = l.id;
    $("review-dialog").showModal();
  }

  $("review-body").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-r]");
    if (!btn) return;
    var l = byId(this.dataset.lead), body = this, r = btn.dataset.r, dlg = $("review-dialog");
    if (r === "close") { dlg.close(); return; }
    if (r === "approve") {
      l.booking.review = "approved"; dlg.close(); toast("Booking approved for " + l.name + "."); renderAll(); return;
    }
    if (r === "change") {
      body.innerHTML = '<h2 id="review-title">Change time</h2><p class="dialog-sub">' + esc(l.name) + " will get an update on WhatsApp.</p>" +
        '<fieldset class="slots"><legend class="visually-hidden">New slot</legend>' + slotRadios(l, "newslot") + "</fieldset>" +
        '<div class="dialog-actions"><button class="btn" type="button" data-r="close">Back out</button><button class="btn btn-primary" type="button" data-r="change-confirm">Change and send update</button></div>';
      return;
    }
    if (r === "change-confirm") {
      var p = body.querySelector('input[name="newslot"]:checked'), s = slotsFor(l)[p ? parseInt(p.value, 10) : 0];
      l.booking.dayOffset = s.day; l.booking.time = s.time; l.booking.dentist = s.dentist;
      l.booking.review = "changed"; l.booking.whatsapp = "sent";
      dlg.close(); toast("Changed to " + dayLabel(s.day) + ", " + s.time + ". Update sent on WhatsApp."); renderAll(); return;
    }
    if (r === "cancel") {
      body.innerHTML = '<h2 id="review-title">Cancel booking</h2><p class="dialog-sub">' + esc(l.name) + " will be told on WhatsApp. Please also call them.</p>" +
        '<label class="label" for="cancel-reason">Reason</label><select class="select" id="cancel-reason"><option value="">Choose a reason</option>' +
        "<option>Wrong treatment or dentist</option><option>Slot no longer available</option><option>Patient needs a different clinic</option><option>Duplicate booking</option></select>" +
        '<p class="error" id="cancel-error" hidden>Choose a reason to cancel.</p>' +
        '<div class="dialog-actions" style="margin-top:14px"><button class="btn" type="button" data-r="close">Keep booking</button><button class="btn btn-primary" type="button" data-r="cancel-confirm">Cancel booking</button></div>';
      return;
    }
    if (r === "cancel-confirm") {
      var reason = $("cancel-reason").value;
      if (!reason) { $("cancel-error").hidden = false; $("cancel-reason").focus(); return; }
      l.status = "closed"; dlg.close();
      toast("Booking cancelled for " + l.name + " (" + reason + "). WhatsApp update sent.");
      renderAll();
    }
  });

  // ---------------------------------------------------------------- actions
  function act(action, l, btn) {
    if (action === "close") { state.selectedId = null; renderList(); renderPanel(); return; }
    if (action === "play") { togglePlay(l); return; }
    if (action === "review") { openReview(l); return; }
    if (action === "book") { openBook(l); return; }
    if (action === "call") {
      if (!l.claimedAt) l.claimedAt = now();
      toast("Calling " + l.name + " on " + l.phone + " from the clinic line.");
      renderAll(); return;
    }
    if (action === "noanswer") {
      var prevO = l.outcome; l.outcome = "no_answer";
      toast("Recorded: no answer for " + l.name + ".", function () { l.outcome = prevO; renderAll(); });
      renderAll(); return;
    }
    if (action === "notinterested") {
      var prev = { status: l.status, outcome: l.outcome };
      if (l.arm === "control") l.outcome = "not_interested"; else l.status = "closed";
      toast(l.name + " marked not interested.", function () { l.status = prev.status; l.outcome = prev.outcome; state.selectedId = l.id; renderAll(); });
      renderAll(); return;
    }
    if (action === "fb-up") { l.feedback = l.feedback === "up" ? null : "up"; l.feedbackReason = null; renderPanel(); return; }
    if (action === "fb-down") { l.feedback = l.feedback === "down" ? null : "down"; if (!l.feedback) l.feedbackReason = null; renderPanel(); return; }
    if (action === "fb-reason") { l.feedbackReason = btn.dataset.reason; renderPanel(); }
  }

  // ---------------------------------------------------------------- events
  $("list").addEventListener("click", function (e) {
    var rv = e.target.closest("[data-review]");
    if (rv) { select(rv.dataset.review, false); openReview(byId(rv.dataset.review)); return; }
    var open = e.target.closest("[data-open]");
    if (open) { select(open.dataset.open, true); return; }
    var row = e.target.closest("[data-row]");
    if (row) select(row.dataset.row, false);
  });

  $("panel").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-action]");
    if (!btn) return;
    var l = byId(state.selectedId);
    if (l || btn.dataset.action === "close") act(btn.dataset.action, l, btn);
  });

  $("tabs").addEventListener("click", function (e) {
    var b = e.target.closest('[role="tab"]');
    if (!b) return;
    state.tab = b.dataset.tab; state.selectedId = null; stopPlayer();
    renderAll();
  });
  $("tabs").addEventListener("keydown", function (e) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    var tabs = Array.prototype.slice.call(this.querySelectorAll('[role="tab"]'));
    var i = tabs.findIndex(function (t) { return t.dataset.tab === state.tab; });
    i = (i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
    state.tab = tabs[i].dataset.tab; state.selectedId = null; stopPlayer();
    renderAll();
    tabs[i].focus();
  });

  $("clinic-filter").addEventListener("change", function () {
    state.clinic = this.value; renderAll();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.selectedId && !document.querySelector("dialog[open]")) {
      state.selectedId = null; stopPlayer(); renderList(); renderPanel();
    }
  });

  // ---------------------------------------------------------------- live tick
  function simulateRetries() {
    var changed = false;
    leads.forEach(function (l) {
      if (l.status !== "no_answer" || !l.nextRetryAt || now() < l.nextRetryAt) return;
      var calls = l.attempts.filter(function (a) { return a.label.indexOf("Call") === 0; }).length + 1;
      l.attempts.push({ label: "Call " + calls, result: "No answer", at: l.nextRetryAt });
      if (calls >= 3) { l.attempts.push({ label: "WhatsApp", result: "Sent", at: l.nextRetryAt }); l.nextRetryAt = null; }
      else l.nextRetryAt = l.nextRetryAt + (calls === 1 ? 5 : 120) * 60000;
      changed = true;
    });
    return changed;
  }

  function tick() {
    $("clock").textContent = clock(now()) + " IST";
    if (simulateRetries()) { renderAll(); return; }
    renderStrip();
    document.querySelectorAll("[data-sla]").forEach(function (el) { var l = byId(el.dataset.sla); if (l) updateSla(el, l); });
    document.querySelectorAll("[data-ago]").forEach(function (el) { var l = byId(el.dataset.ago); if (l) el.textContent = minsAgo(l.enquiredAt); });
    document.querySelectorAll("[data-retry]").forEach(function (el) { var l = byId(el.dataset.retry); if (l && l.nextRetryAt) el.textContent = inMins(l.nextRetryAt); });
  }

  // ---------------------------------------------------------------- init
  renderAll();
  tick();
  setInterval(tick, 1000);
})();
