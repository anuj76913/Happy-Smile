/* Browser voice demo for staff: practice calls (/v1/test-calls) driven by the shared voice loop
   in /static/shared/voicecall.js. Nothing is booked. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var TAGS = { asked_person: "Asked for a person", pain_swelling: "Pain or swelling (urgent)", emergency: "Emergency", distress: "Distress",
    price_emi: "Price/EMI question", clinical: "Clinical question", couldnt_understand: "Couldn't understand", no_suitable_slot: "No suitable slot",
    minor: "Under 18", recording_objection: "Didn't want recording", needs_staff: "Needs staff help", system_fallback: "System fallback",
    booking_paused: "AI booking paused", abusive: "Abusive" };
  var callId = null;

  function api(path, body) {
    var opts = { method: body ? "POST" : "GET", credentials: "same-origin", headers: { Accept: "application/json" } };
    if (body) { opts.headers["Content-Type"] = "application/json"; opts.headers["X-Requested-With"] = "hs-console"; opts.body = JSON.stringify(body); }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.detail || "Request failed"); e.status = r.status; throw e; }
        return j;
      });
    });
  }

  var call = window.HSVoiceCall({
    el: { dot: $("v-dot"), state: $("v-state"), log: $("v-log"), interim: $("v-interim") },
    uiLang: "en",  // staff UI stays English; speech follows the call's language
    turn: function (payload) { return api("/v1/test-calls/" + callId + "/turn", payload); },
    onLang: function (lang) { $("v-lang-tag").textContent = lang === "hi" ? "हिन्दी · hi-IN" : "English · en-IN"; },
    onReply: function (r, line) {
      (r.guard_events || []).forEach(function (g) { if (g.type === "triggers") line("system", "Guardrail: " + g.triggers.join(", ")); });
    },
    onEnd: function (r) {
      var parts = ["Call ended: " + (r.outcome || "ended")];
      if (r.handover) parts.push("handed to staff: " + (TAGS[r.handover.reason] || r.handover.reason) + (r.handover.urgency === "urgent" ? " (urgent)" : ""));
      if (r.booking) parts.push("would book " + new Date(r.booking.start_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) + " with " + r.booking.dentist + " (practice: not saved)");
      if (r.summary) parts.push("Summary: " + r.summary.lines.join(" "));
      $("v-result").textContent = parts.join(" · ");
      $("v-result").hidden = false; $("v-again").hidden = false;
    },
    onError: function (e, line) {
      line("system", e.status === 401 ? "Your session ended. Sign in to the console again." : "Something went wrong: " + e.message);
    }
  });

  $("v-start").addEventListener("click", function () {
    var lang = $("v-lang").value;
    $("v-start").disabled = true;
    api("/v1/test-calls", { name: $("v-name").value, treatment: $("v-treatment").value, clinic_id: $("v-clinic").value, language: lang })
      .then(function (r) {
        callId = r.id;
        $("setup").hidden = true; $("call").hidden = false; $("v-result").hidden = true; $("v-again").hidden = true;
        call.start(r.say, r.lang || lang);
      }).catch(function (e) { alert(e.message); }).then(function () { $("v-start").disabled = false; });
  });
  $("v-skip").addEventListener("click", call.skip);
  $("v-listen").addEventListener("click", call.listenAgain);
  $("v-hangup").addEventListener("click", call.hangup);
  $("v-type").addEventListener("submit", function (e) {
    e.preventDefault();
    var t = $("v-text").value.trim(); if (!t) return;
    $("v-text").value = ""; call.typed(t);
  });
  $("v-again").addEventListener("click", function () { call.stop(); $("call").hidden = true; $("setup").hidden = false; });

  $("no-speech").hidden = call.supported;
  api("/v1/auth/me").then(function (me) {
    var sel = $("v-clinic");
    me.clinics.forEach(function (c) { sel.appendChild(new Option(c.name, c.id)); });
    $("setup").hidden = false;
  }).catch(function () { $("signin-needed").hidden = false; });
})();
