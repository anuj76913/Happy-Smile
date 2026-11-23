/* Public enquiry form (plan P2-03). Talks to /v1/enquiry-config and /v1/enquiries. */
(function () {
  "use strict";

  var T = {
    en: {
      brandSub: "Dental clinics", title: "Request a call",
      subtitle: "Tell us what you are interested in and we will call you back.",
      langLabel: "Language for the call", nameLabel: "Your name", mobileLabel: "Mobile number",
      mobileHint: "10-digit Indian mobile number", treatmentLabel: "What are you interested in?",
      tBraces: "Braces / aligners", tWhitening: "Whitening", tImplants: "Implants", tOther: "Other",
      otherLabel: "Tell us briefly", otherPlaceholder: "Tell us briefly (optional)",
      clinicLabel: "Nearest clinic", clinicPlaceholder: "Choose a clinic", prefLabel: "How should we contact you?",
      prefNowTeam: "Call me back", prefNowTeamSub: "During clinic hours, 9 am to 9 pm",
      prefNowAssist: "Call me now", prefNowAssistSub: "Usually within a few minutes",
      prefLater: "Call me at a time I pick", prefLaterSub: "Between 9 am and 9 pm",
      prefWa: "WhatsApp me instead", prefWaSub: "No call. Our team replies on WhatsApp",
      dayLabel: "Day", timeLabel: "Time", today: "Today", tomorrow: "Tomorrow",
      submit: "Request my call", submitWa: "Message me on WhatsApp", submitting: "Sending...",
      submitHint: "Tick the box above to continue.",
      wordingChanged: "The wording above was just updated. Please read it and tick the box again.",
      err: { required: "Please fill this in.", too_long: "This is too long.", invalid_mobile: "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.",
             invalid: "Please choose an option.", outside_calling_hours: "Pick a time between 9 am and 9 pm, within the next 7 days." },
      nameRequired: "Please enter your name.", clinicRequired: "Please choose a clinic.",
      rateLimited: "We have received several requests from you already. Please try again later, or call your clinic.",
      network: "We couldn't send your request. Check your connection and try again.",
      loadError: "We couldn't load this page properly. Please refresh, or call your nearest clinic.",
      server: "Something went wrong on our side. Please try again.",
      expectTitle: "What to expect", restart: "Make another request",
      ref: function (r) { return "Your reference: " + r; },
      tTeamCall: "Thank you. We have your request", tTeamCallSub: function (c) { return "Our " + c + " team will call you back during clinic hours, 9 am to 9 pm."; },
      tTeamWa: "Thank you. Check WhatsApp soon", tTeamWaSub: function (c) { return "Our " + c + " team will message you on WhatsApp during clinic hours."; },
      tSched: function (w) { return "We will call you " + w; }, tSchedSub: "If the time no longer suits you, reply to our WhatsApp message.",
      tDup: "We already have your request", tDupSub: function (c) { return "You asked us earlier today. Our " + c + " team will be in touch, so there is no need to submit again."; },
      tAssistNow: "Your call is on its way", tAssistNowSub: function (c) { return "HappySmile's virtual assistant will call you about your enquiry at " + c + "."; },
      tAssistLater: "We will call you after 9 am tomorrow", tAssistLaterSub: "Our calling hours are 9 am to 9 pm.",
      countdown: "until the call", calling: "Calling you now", callingSub: "Please pick up. If you miss it, we will try again in 5 minutes.",
      callerFrom: "The call will come from", callerHint: "Save this number so you recognise the call.",
      expectTeam: ["Someone from the clinic will call you, and can book a consultation.", "You can ask any questions about cost or treatment on the call.", "If you are in pain or have swelling, tell us so we can see you sooner."],
      expectWa: ["Our team replies during clinic hours, 9 am to 9 pm.", "You can ask for a call at any time in the chat.", "Reply STOP to stop messages."],
      expectAssist: ["It will say it is HappySmile's virtual assistant.", "It can book a consultation for you, or ask our team to call you.", "Say “talk to a person” at any time.", "If you are in pain or have swelling, tell it. A team member will call you first."],
      when: function (dayIdx, label, timeStr) { return (dayIdx === 0 ? "today" : dayIdx === 1 ? "tomorrow" : "on " + label) + " at " + timeStr; },
      // demo phone line (development only)
      demoNote: "Demo phone line: the assistant will ring this browser tab, not your phone. Keep this tab open.",
      incoming: "Incoming call", assistantName: "HappySmile assistant", ringHint: "Answer to talk with your microphone (Chrome or Edge works best).",
      answer: "Answer", decline: "Decline", hangup: "Hang up", speakAgain: "Speak again", typeLabel: "Or type your reply", sendBtn: "Send", done: "Done",
      missed: function (time) { return "You missed our call. We will try again at " + time + "."; },
      demoStaff: "The assistant isn't calling for this enquiry; our team will call you instead.",
      demoEnded: "We couldn't reach you, so our team will follow up.", callOver: "The call has already ended.",
      outcome: { booked: ["Your consultation is booked", "The time and clinic are in the call above. See you soon!"],
                 handover: ["Our team will call you", "A team member from the clinic will call you back shortly."],
                 callback: ["We will call you back", "We will call you again at the time you asked for."],
                 other: ["Call ended", "Thank you for talking to us. Our team will follow up if needed."] },
      callFinished: function (title) { return "Call finished: " + title + "."; },
      demoPick: function (names) { return "Voice demo: choose " + names.join(", ") + " to get a call from the assistant in this tab."; },
      demoNotThis: function (names) { return "Voice demo: this clinic isn't in the assistant pilot, so the team would call instead. Choose " + names.join(", ") + " for the assistant."; },
      demoNoClinics: "Voice demo: no clinic has the assistant switched on. Restart with run-dev.ps1 -VoiceDemo.",
      demoTeam: "Voice demo: this enquiry went to the clinic team, so the assistant won't ring this tab. Make another request at a pilot clinic."
    },
    hi: {
      brandSub: "डेंटल क्लिनिक", title: "कॉल का अनुरोध करें",
      subtitle: "बताइए आप किसमें रुचि रखते हैं, हम आपको कॉल करेंगे।",
      langLabel: "कॉल की भाषा", nameLabel: "आपका नाम", mobileLabel: "मोबाइल नंबर",
      mobileHint: "10 अंकों का भारतीय मोबाइल नंबर", treatmentLabel: "आप किसमें रुचि रखते हैं?",
      tBraces: "ब्रेसेस / अलाइनर", tWhitening: "दाँतों की सफ़ेदी", tImplants: "इम्प्लांट", tOther: "अन्य",
      otherLabel: "संक्षेप में बताइए", otherPlaceholder: "संक्षेप में बताइए (वैकल्पिक)",
      clinicLabel: "नज़दीकी क्लिनिक", clinicPlaceholder: "क्लिनिक चुनें", prefLabel: "हम आपसे कैसे संपर्क करें?",
      prefNowTeam: "मुझे कॉल करें", prefNowTeamSub: "क्लिनिक के समय में, सुबह 9 से रात 9 बजे",
      prefNowAssist: "मुझे अभी कॉल करें", prefNowAssistSub: "आमतौर पर कुछ ही मिनटों में",
      prefLater: "मेरे चुने समय पर कॉल करें", prefLaterSub: "सुबह 9 से रात 9 बजे के बीच",
      prefWa: "कॉल के बजाय WhatsApp करें", prefWaSub: "कोई कॉल नहीं। हमारी टीम WhatsApp पर जवाब देगी",
      dayLabel: "दिन", timeLabel: "समय", today: "आज", tomorrow: "कल",
      submit: "मेरी कॉल का अनुरोध करें", submitWa: "मुझे WhatsApp पर मैसेज करें", submitting: "भेजा जा रहा है...",
      submitHint: "आगे बढ़ने के लिए ऊपर दिए बॉक्स पर टिक करें।",
      wordingChanged: "ऊपर लिखी जानकारी अभी बदली गई है। कृपया इसे पढ़कर बॉक्स पर फिर से टिक करें।",
      err: { required: "कृपया यह भरें।", too_long: "यह बहुत लंबा है।", invalid_mobile: "6, 7, 8 या 9 से शुरू होने वाला 10 अंकों का मोबाइल नंबर लिखें।",
             invalid: "कृपया एक विकल्प चुनें।", outside_calling_hours: "अगले 7 दिनों में सुबह 9 से रात 9 बजे के बीच का समय चुनें।" },
      nameRequired: "कृपया अपना नाम लिखें।", clinicRequired: "कृपया एक क्लिनिक चुनें।",
      rateLimited: "हमें आपसे पहले ही कई अनुरोध मिल चुके हैं। कृपया बाद में कोशिश करें या अपने क्लिनिक को कॉल करें।",
      network: "आपका अनुरोध नहीं भेजा जा सका। अपना कनेक्शन जाँचें और फिर से कोशिश करें।",
      loadError: "यह पेज ठीक से लोड नहीं हुआ। कृपया रीफ़्रेश करें या अपने नज़दीकी क्लिनिक को कॉल करें।",
      server: "हमारी ओर से कुछ गड़बड़ हुई। कृपया फिर से कोशिश करें।",
      expectTitle: "आगे क्या होगा", restart: "एक और अनुरोध करें",
      ref: function (r) { return "आपका रेफ़रेंस: " + r; },
      tTeamCall: "धन्यवाद। हमें आपका अनुरोध मिल गया है", tTeamCallSub: function (c) { return "हमारी " + c + " टीम क्लिनिक के समय, सुबह 9 से रात 9 बजे के बीच, आपको कॉल करेगी।"; },
      tTeamWa: "धन्यवाद। जल्द ही WhatsApp देखें", tTeamWaSub: function (c) { return "हमारी " + c + " टीम क्लिनिक के समय में आपको WhatsApp पर मैसेज करेगी।"; },
      tSched: function (w) { return "हम आपको " + w + " कॉल करेंगे"; }, tSchedSub: "अगर समय बदलना हो, तो हमारे WhatsApp मैसेज का जवाब दें।",
      tDup: "हमें आपका अनुरोध पहले ही मिल चुका है", tDupSub: function (c) { return "आपने आज पहले ही अनुरोध किया था। हमारी " + c + " टीम आपसे संपर्क करेगी, फिर से भेजने की ज़रूरत नहीं है।"; },
      tAssistNow: "आपकी कॉल आ रही है", tAssistNowSub: function (c) { return "HappySmile की वर्चुअल असिस्टेंट " + c + " क्लिनिक की ओर से आपको कॉल करेगी।"; },
      tAssistLater: "हम कल सुबह 9 बजे के बाद आपको कॉल करेंगे", tAssistLaterSub: "हमारे कॉल का समय सुबह 9 से रात 9 बजे तक है।",
      countdown: "कॉल आने में", calling: "अभी आपको कॉल कर रहे हैं", callingSub: "कृपया कॉल उठाएँ। अगर छूट जाए, तो हम 5 मिनट बाद फिर कोशिश करेंगे।",
      callerFrom: "कॉल इस नंबर से आएगी", callerHint: "यह नंबर सेव कर लें ताकि आप कॉल पहचान सकें।",
      expectTeam: ["क्लिनिक से कोई आपको कॉल करेगा और कंसल्टेशन बुक कर सकता है।", "कॉल पर आप खर्च या इलाज के बारे में कोई भी सवाल पूछ सकते हैं।", "अगर दर्द या सूजन है, तो हमें बताएँ ताकि हम आपको जल्दी देख सकें।"],
      expectWa: ["हमारी टीम क्लिनिक के समय, सुबह 9 से रात 9 बजे तक, जवाब देती है।", "चैट में आप कभी भी कॉल के लिए कह सकते हैं।", "मैसेज बंद करने के लिए STOP लिखें।"],
      expectAssist: ["वह बताएगी कि वह HappySmile की वर्चुअल असिस्टेंट है।", "वह आपकी कंसल्टेशन बुक कर सकती है या हमारी टीम से आपको कॉल करवा सकती है।", "किसी भी समय “किसी इंसान से बात करनी है” कहें।", "अगर दर्द या सूजन है, तो बताएँ। हमारी टीम का सदस्य पहले आपको कॉल करेगा।"],
      when: function (dayIdx, label, timeStr) { return (dayIdx === 0 ? "आज " : dayIdx === 1 ? "कल " : label + " को ") + timeStr + " बजे"; },
      demoNote: "डेमो फ़ोन लाइन: असिस्टेंट आपके फ़ोन पर नहीं, इसी ब्राउज़र टैब में कॉल करेगी। यह टैब खुला रखें।",
      incoming: "इनकमिंग कॉल", assistantName: "HappySmile असिस्टेंट", ringHint: "माइक्रोफ़ोन से बात करने के लिए कॉल उठाएँ (Chrome या Edge सबसे अच्छा है)।",
      answer: "उठाएँ", decline: "काटें", hangup: "कॉल काटें", speakAgain: "फिर से बोलें", typeLabel: "या अपना जवाब लिखें", sendBtn: "भेजें", done: "ठीक है",
      missed: function (time) { return "आपकी कॉल छूट गई। हम " + time + " पर फिर कोशिश करेंगे।"; },
      demoStaff: "इस अनुरोध पर असिस्टेंट कॉल नहीं करेगी; हमारी टीम आपको कॉल करेगी।",
      demoEnded: "हम आपसे संपर्क नहीं कर सके, इसलिए हमारी टीम आपसे संपर्क करेगी।", callOver: "कॉल पहले ही समाप्त हो चुकी है।",
      outcome: { booked: ["आपकी कंसल्टेशन बुक हो गई है", "समय और क्लिनिक ऊपर कॉल में बताए गए हैं। जल्द मिलते हैं!"],
                 handover: ["हमारी टीम आपको कॉल करेगी", "क्लिनिक की टीम का सदस्य जल्द ही आपको कॉल करेगा।"],
                 callback: ["हम आपको फिर कॉल करेंगे", "आपके बताए समय पर हम फिर कॉल करेंगे।"],
                 other: ["कॉल समाप्त", "हमसे बात करने के लिए धन्यवाद। ज़रूरत हुई तो हमारी टीम संपर्क करेगी।"] },
      callFinished: function (title) { return "कॉल समाप्त: " + title + "।"; },
      demoPick: function (names) { return "वॉइस डेमो: इस टैब में असिस्टेंट की कॉल के लिए " + names.join(", ") + " चुनें।"; },
      demoNotThis: function (names) { return "वॉइस डेमो: यह क्लिनिक असिस्टेंट पायलट में नहीं है, इसलिए टीम कॉल करेगी। असिस्टेंट के लिए " + names.join(", ") + " चुनें।"; },
      demoNoClinics: "वॉइस डेमो: किसी क्लिनिक में असिस्टेंट चालू नहीं है। run-dev.ps1 -VoiceDemo से फिर शुरू करें।",
      demoTeam: "वॉइस डेमो: यह अनुरोध क्लिनिक टीम को गया है, इसलिए असिस्टेंट इस टैब में कॉल नहीं करेगी। किसी पायलट क्लिनिक के लिए नया अनुरोध करें।"
    }
  };

  var $ = function (id) { return document.getElementById(id); };
  var form = $("request-form");
  var lang = "en";
  var cfg = null;
  var skewMs = 0;
  var token = newToken();
  var submitting = false;
  var countdownTimer = null;

  function newToken() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, function (c) {
      return (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16);
    });
  }
  function t(k) { return T[lang][k]; }
  function checked(n) { var el = form.querySelector('input[name="' + n + '"]:checked'); return el ? el.value : null; }

  // ---------------------------------------------------------------- IST time helpers (server clock)
  function nowServer() { return new Date(Date.now() + skewMs); }
  function istParts(d) {
    var p = {};
    new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "short" }).formatToParts(d)
      .forEach(function (x) { p[x.type] = x.value; });
    return p;
  }
  function fmtTime(mins) {
    var h = Math.floor(mins / 60), m = mins % 60;
    return (h % 12 || 12) + ":" + (m < 10 ? "0" : "") + m + (h >= 12 ? " pm" : " am");
  }
  function hhmmToMin(s) { var a = s.split(":"); return +a[0] * 60 + +a[1]; }

  // ---------------------------------------------------------------- config + rendering
  function currentClinic() {
    var id = $("clinic").value;
    return cfg && cfg.clinics.filter(function (c) { return c.id === id; })[0];
  }
  function currentDisclosure() { var c = currentClinic(); return c ? c.disclosure : cfg.default_disclosure; }

  function loadConfig(keepClinic) {
    return fetch("/v1/enquiry-config?lang=" + lang, { headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        cfg = data;
        skewMs = Date.parse(data.now) - Date.now();
        var sel = $("clinic"), prev = keepClinic ? sel.value : "";
        sel.querySelectorAll("option[value]:not([value=''])").forEach(function (o) { o.remove(); });
        data.clinics.forEach(function (c) {
          var o = document.createElement("option"); o.value = c.id; o.textContent = c.name; sel.appendChild(o);
        });
        sel.value = prev;
        $("load-error").hidden = true;
        render();
      })
      .catch(function () { $("load-error").textContent = t("loadError"); $("load-error").hidden = false; });
  }

  function render() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var v = t(el.getAttribute("data-i18n")); if (typeof v === "string") el.textContent = v;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) { el.placeholder = t(el.getAttribute("data-i18n-placeholder")); });
    if (!cfg) return;
    var d = currentDisclosure();
    var assist = d.variant === "assistant";
    $("pref-now-title").textContent = assist ? t("prefNowAssist") : t("prefNowTeam");
    $("pref-now-sub").textContent = assist ? t("prefNowAssistSub") : t("prefNowTeamSub");
    $("disclosure").textContent = d.disclosure;
    // Demo phone line: only clinics whose wording says "virtual assistant" get the browser call.
    var demoClinics = cfg.clinics.filter(function (c) { return c.disclosure.variant === "assistant"; }).map(function (c) { return c.name; });
    var hint = !cfg.browser_calls ? "" : !demoClinics.length ? t("demoNoClinics")
      : !$("clinic").value ? T[lang].demoPick(demoClinics) : !assist ? T[lang].demoNotThis(demoClinics) : "";
    $("clinic-demo-hint").textContent = hint; $("clinic-demo-hint").hidden = !hint;
    $("consent-text").textContent = d.consent;
    buildSchedule(true);
    updateSubmit();
  }

  function buildSchedule(keep) {
    if (!cfg) return;
    var daySel = $("sched-day"), prevDay = keep ? daySel.value : "";
    var start = hhmmToMin(cfg.calling_window.start), end = hhmmToMin(cfg.calling_window.end) - cfg.calling_window.last_call_cutoff_min;
    var now = istParts(nowServer()), nowMin = +now.hour * 60 + +now.minute;
    daySel.innerHTML = "";
    for (var i = 0; i < 7; i++) {
      if (i === 0 && Math.ceil((nowMin + 30) / 30) * 30 > end) continue;
      var d = new Date(nowServer().getTime() + i * 86400000);
      var label = i === 0 ? t("today") : i === 1 ? t("tomorrow")
        : d.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" });
      var o = document.createElement("option"); o.value = String(i); o.textContent = label; daySel.appendChild(o);
    }
    if (prevDay && daySel.querySelector('option[value="' + prevDay + '"]')) daySel.value = prevDay;
    buildTimes(start, end, nowMin);
  }

  function buildTimes(start, end, nowMin) {
    var timeSel = $("sched-time"), prev = timeSel.value;
    if (start === undefined) {
      start = hhmmToMin(cfg.calling_window.start); end = hhmmToMin(cfg.calling_window.end) - cfg.calling_window.last_call_cutoff_min;
      var n = istParts(nowServer()); nowMin = +n.hour * 60 + +n.minute;
    }
    var first = $("sched-day").value === "0" ? Math.max(start, Math.ceil((nowMin + 30) / 30) * 30) : start;
    timeSel.innerHTML = "";
    for (var m = first; m <= end; m += 30) {
      var o = document.createElement("option"); o.value = String(m); o.textContent = fmtTime(m); timeSel.appendChild(o);
    }
    if (prev && timeSel.querySelector('option[value="' + prev + '"]')) timeSel.value = prev;
    else if ($("sched-day").value !== "0" && timeSel.querySelector('option[value="1080"]')) timeSel.value = "1080";
  }

  function scheduledIso() {
    var dayIdx = +$("sched-day").value, mins = +$("sched-time").value;
    var p = istParts(new Date(nowServer().getTime() + dayIdx * 86400000));
    var hh = String(Math.floor(mins / 60)).padStart(2, "0"), mm = String(mins % 60).padStart(2, "0");
    return p.year + "-" + p.month + "-" + p.day + "T" + hh + ":" + mm + ":00+05:30";
  }

  function updateSubmit() {
    var btn = $("submit");
    btn.textContent = submitting ? t("submitting") : checked("pref") === "whatsapp" ? t("submitWa") : t("submit");
    btn.disabled = submitting || !$("consent").checked || !cfg;
    $("submit-hint").hidden = $("consent").checked;
  }

  // ---------------------------------------------------------------- validation + errors
  function normaliseMobile(raw) {
    var d = (raw || "").replace(/\D/g, "");
    if (d.length === 12 && d.indexOf("91") === 0) d = d.slice(2); else if (d.length === 11 && d[0] === "0") d = d.slice(1);
    return d;
  }
  function setError(field, msg) {
    var input = $(field === "scheduled_at" ? "sched-time" : field), err = $(field + "-error");
    if (!err) return;
    if (msg) { if (input) input.setAttribute("aria-invalid", "true"); err.textContent = msg; err.hidden = false; }
    else { if (input) input.removeAttribute("aria-invalid"); err.hidden = true; err.textContent = ""; }
  }
  function clientValidate() {
    var ok = true;
    if (!$("name").value.trim()) { setError("name", t("nameRequired")); ok = false; } else setError("name");
    if (!/^[6-9]\d{9}$/.test(normaliseMobile($("mobile").value))) { setError("mobile", t("err").invalid_mobile); ok = false; } else setError("mobile");
    if (!$("clinic").value) { setError("clinic", t("clinicRequired")); ok = false; } else setError("clinic");
    var firstBad = form.querySelector('[aria-invalid="true"]'); if (firstBad) firstBad.focus();
    return ok;
  }
  function showSubmitError(msg) { var e = $("submit-error"); e.textContent = msg; e.hidden = !msg; }

  // ---------------------------------------------------------------- submit
  function payload() {
    var pref = checked("pref");
    return {
      client_token: token, name: $("name").value, mobile: $("mobile").value, treatment: checked("treatment"),
      treatment_other: checked("treatment") === "other" ? $("other").value : null, clinic_id: $("clinic").value,
      language: lang, contact_pref: pref, scheduled_at: pref === "scheduled" ? scheduledIso() : null,
      consent: $("consent").checked, disclosure_version: currentDisclosure().version
    };
  }

  function send(body, attempt) {
    return fetch("/v1/enquiries", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, body: j }; }); })
      .catch(function (err) {
        // Network failure: retry once with the same token; the server returns the original result if it got the first one.
        if (attempt < 1) return new Promise(function (res) { setTimeout(res, 1500); }).then(function () { return send(body, attempt + 1); });
        throw err;
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (submitting || !$("consent").checked) return;
    showSubmitError("");
    if (!clientValidate()) return;
    submitting = true; updateSubmit();
    if (cfg && cfg.browser_calls) demoAudioUnlock();  // the click lets the ringtone play later
    var body = payload();
    send(body, 0).then(function (res) {
      submitting = false; updateSubmit();
      if (res.status === 201 || res.status === 200) { token = newToken(); showConfirmation(res.body, body.client_token); return; }
      if (res.status === 422) {
        token = newToken();
        Object.keys(res.body.fields || {}).forEach(function (f) { setError(f, t("err")[res.body.fields[f]] || t("err").invalid); });
        var bad = form.querySelector('[aria-invalid="true"]'); if (bad) bad.focus();
        if (res.body.fields && res.body.fields.consent) showSubmitError(t("submitHint"));
        return;
      }
      if (res.status === 409 && res.body.error === "disclosure_changed") {
        token = newToken();
        var c = currentClinic(); if (c) c.disclosure = res.body.disclosure;
        $("consent").checked = false; $("wording-changed").hidden = false; render(); $("disclosure").focus();
        return;
      }
      if (res.status === 429) { showSubmitError(t("rateLimited")); return; }
      showSubmitError(t("server"));
    }).catch(function () { submitting = false; updateSubmit(); showSubmitError(t("network")); });
  });

  // ---------------------------------------------------------------- confirmation
  function showConfirmation(r, submittedToken) {
    var c = r.contact, clinic = r.clinic, title, sub, expect;
    $("caller-card").hidden = true; $("countdown").hidden = true; stopCountdown(); demoStop();
    if (r.deduplicated) { title = t("tDup"); sub = T[lang].tDupSub(clinic); expect = c.who === "assistant" ? t("expectAssist") : t("expectTeam"); }
    else if (c.when === "scheduled") {
      var p = istParts(new Date(c.scheduled_at)), n = istParts(nowServer());
      var dayIdx = Math.round((Date.UTC(+p.year, +p.month - 1, +p.day) - Date.UTC(+n.year, +n.month - 1, +n.day)) / 86400000);
      var label = new Date(c.scheduled_at).toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata", weekday: "long" });
      title = T[lang].tSched(T[lang].when(dayIdx, label, fmtTime(+p.hour * 60 + +p.minute)));
      sub = t("tSchedSub"); expect = c.who === "assistant" ? t("expectAssist") : t("expectTeam");
    } else if (c.channel === "whatsapp") { title = t("tTeamWa"); sub = T[lang].tTeamWaSub(clinic); expect = t("expectWa"); }
    else if (c.who === "assistant" && c.when === "now") { title = t("tAssistNow"); sub = T[lang].tAssistNowSub(clinic); expect = t("expectAssist"); startCountdown(c.eta_seconds || 120); }
    else if (c.who === "assistant") { title = t("tAssistLater"); sub = t("tAssistLaterSub"); expect = t("expectAssist"); }
    else { title = t("tTeamCall"); sub = T[lang].tTeamCallSub(clinic); expect = t("expectTeam"); }

    if (c.caller_id) {
      $("caller-card").hidden = false; $("caller-label").textContent = t("callerFrom");
      $("caller-number").textContent = c.caller_id; $("caller-hint").textContent = t("callerHint");
    }
    $("confirm-title").textContent = title; $("confirm-sub").textContent = sub;
    var ul = $("expect"); ul.innerHTML = "";
    expect.forEach(function (line) { var li = document.createElement("li"); li.textContent = line; ul.appendChild(li); });
    $("ref-line").textContent = T[lang].ref(r.ref);
    $("form-view").hidden = true; $("confirm-view").hidden = false; $("confirm-title").focus(); window.scrollTo(0, 0);
    if (cfg && cfg.browser_calls && !r.deduplicated && c.who === "assistant" && c.channel !== "whatsapp") demoStart(submittedToken, c.caller_id);
    else if (cfg && cfg.browser_calls) demoNote(t("demoTeam"));
  }

  // ---------------------------------------------------------------- demo phone line (development only)
  // With TELEPHONY_PROVIDER=browser the worker "dials" this tab: we poll /v1/demo-call/{token},
  // ring when the call is placed, and run the conversation through the real call path.
  var demo = { token: null, callerId: "", poll: null, until: 0, inCall: false, ringing: false, audio: null, ringTimer: null, clock: null, call: null };

  function demoNote(msg) { $("demo-note").textContent = msg || ""; $("demo-note").hidden = !msg; }
  function demoApi(path, body) {
    var o = { method: body ? "POST" : "GET", headers: { Accept: "application/json" } };
    if (body) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); }
    return fetch("/v1/demo-call/" + demo.token + path, o).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.detail || "Request failed"); e.status = r.status; throw e; }
        return j;
      });
    });
  }
  function demoStart(tok, callerId) {
    demo.token = tok; demo.callerId = callerId || ""; demo.until = Date.now() + 20 * 60000; demo.inCall = false;
    demoNote(t("demoNote"));
    demoPoll();
  }
  function demoStop() {
    clearTimeout(demo.poll); demo.poll = null; demo.token = null; stopRinging();
    if (demo.call) demo.call.stop();
    if (demo.clock) { clearInterval(demo.clock); demo.clock = null; }
    demo.inCall = false; demoNote("");
    $("ring-view").hidden = true; $("call-view").hidden = true;
  }
  function demoPoll() {
    clearTimeout(demo.poll);
    if (!demo.token || demo.inCall || Date.now() > demo.until) return;
    var tok = demo.token;
    demoApi("").then(function (s) { if (tok === demo.token) demoApply(s); })
      .catch(function (e) { if (e.status !== 404 && tok === demo.token) demo.poll = setTimeout(demoPoll, 4000); });
  }
  function demoApply(s) {
    if (demo.inCall) return;
    if (s.state === "ringing") { showRinging(); demo.poll = setTimeout(demoPoll, 1500); return; }
    if (demo.ringing) { stopRinging(); $("ring-view").hidden = true; $("confirm-view").hidden = false; }
    if (s.state === "queued") {
      if (s.retry) { var p = istParts(new Date(s.due_at)); demoNote(T[lang].missed(fmtTime(+p.hour * 60 + +p.minute))); }
      demo.poll = setTimeout(demoPoll, 1500);
    } else if (s.state === "staff") demoNote(t("demoStaff"));
    else if (s.state === "ended") demoNote(s.outcome === "no_answer" || s.outcome === "busy" ? t("demoEnded") : t("callOver"));
  }

  // Ringtone: Indian double ring (400 + 450 Hz) through WebAudio. Browsers only allow sound after a
  // click, so the submit click creates the AudioContext.
  function demoAudioUnlock() {
    try {
      if (!demo.audio) { var AC = window.AudioContext || window.webkitAudioContext; if (AC) demo.audio = new AC(); }
      if (demo.audio && demo.audio.state === "suspended") demo.audio.resume();
    } catch (e) { demo.audio = null; }
  }
  function ringBurst() {
    var ctx = demo.audio; if (!ctx || ctx.state !== "running") return;
    var gain = ctx.createGain(); gain.gain.value = 0; gain.connect(ctx.destination);
    [400, 450].forEach(function (f) { var o = ctx.createOscillator(); o.frequency.value = f; o.connect(gain); o.start(); o.stop(ctx.currentTime + 1.05); });
    var t0 = ctx.currentTime;
    [[0, 0.4], [0.6, 1.0]].forEach(function (seg) {
      gain.gain.setValueAtTime(0.08, t0 + seg[0]); gain.gain.setValueAtTime(0, t0 + seg[1]);
    });
  }
  function showRinging() {
    if (demo.ringing) return;
    demo.ringing = true;
    stopCountdown(); $("countdown").hidden = true;
    $("ring-label").textContent = t("incoming"); $("ring-title").textContent = t("assistantName");
    $("ring-number").textContent = demo.callerId; $("ring-hint").textContent = t("ringHint");
    $("ring-answer").textContent = t("answer"); $("ring-decline").textContent = t("decline");
    $("ring-answer").disabled = false; $("ring-decline").disabled = false;
    $("confirm-view").hidden = true; $("ring-view").hidden = false; $("ring-answer").focus(); window.scrollTo(0, 0);
    ringBurst(); demo.ringTimer = setInterval(ringBurst, 3000);
    if (navigator.vibrate) navigator.vibrate([400, 200, 400]);
  }
  function stopRinging() { demo.ringing = false; if (demo.ringTimer) { clearInterval(demo.ringTimer); demo.ringTimer = null; } }

  function startCall(r) {
    demo.inCall = true; clearTimeout(demo.poll);
    $("ring-view").hidden = true; $("call-view").hidden = false; $("call-result").hidden = true;
    $("c-type").hidden = false; $("c-controls").hidden = false;
    $("call-title").textContent = t("assistantName"); $("c-listen").textContent = t("speakAgain"); $("c-hangup").textContent = t("hangup");
    $("c-text-label").textContent = t("typeLabel"); $("c-text").placeholder = t("typeLabel"); $("c-send").textContent = t("sendBtn");
    var started = Date.now();
    demo.clock = setInterval(function () {
      var s = Math.floor((Date.now() - started) / 1000); $("call-timer").textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    }, 500);
    demo.call = window.HSVoiceCall({
      el: { dot: $("c-dot"), state: $("c-state"), log: $("c-log"), interim: $("c-interim") },
      turn: function (payload) { return demoApi("/turn", payload); },
      onEnd: endCall,
      onError: function (e) { if (e.status === 409) endCall({ result: { outcome: null } }); }
    });
    demo.call.start(r.say, r.lang);
  }
  function endCall(r) {
    if (demo.clock) { clearInterval(demo.clock); demo.clock = null; }
    var o = r.outcome || (r.result && r.result.outcome);
    var pair = T[lang].outcome[o] || T[lang].outcome.other;
    $("result-title").textContent = pair[0]; $("result-sub").textContent = pair[1]; $("call-done").textContent = t("done");
    $("c-type").hidden = true; $("c-controls").hidden = true; $("call-result").hidden = false;
    demoNote(T[lang].callFinished(pair[0]));
    demo.token = null;  // this enquiry's demo is over
  }

  $("ring-answer").addEventListener("click", function () {
    stopRinging(); demoAudioUnlock();
    $("ring-answer").disabled = true; $("ring-decline").disabled = true;
    demoApi("/answer", {}).then(startCall).catch(function () {
      $("ring-view").hidden = true; $("confirm-view").hidden = false; demoNote(t("callOver")); demoPoll();
    });
  });
  $("ring-decline").addEventListener("click", function () {
    stopRinging();
    $("ring-answer").disabled = true; $("ring-decline").disabled = true;
    demoApi("/decline", {}).then(demoApply).catch(function () { demoPoll(); })
      .then(function () { $("ring-view").hidden = true; $("confirm-view").hidden = false; });
  });
  $("c-listen").addEventListener("click", function () { if (demo.call) demo.call.listenAgain(); });
  $("c-hangup").addEventListener("click", function () { if (demo.call) demo.call.hangup(); });
  $("c-type").addEventListener("submit", function (e) {
    e.preventDefault();
    var v = $("c-text").value.trim(); if (!v || !demo.call) return;
    $("c-text").value = ""; demo.call.typed(v);
  });
  $("call-done").addEventListener("click", function () {
    if (demo.call) demo.call.stop();
    $("call-view").hidden = true; $("confirm-view").hidden = false; $("confirm-title").focus();
  });
  window.addEventListener("pagehide", function () {
    // Closing the tab mid-call is a hang-up (the worker would also time it out after 5 minutes).
    if (demo.inCall && demo.token && demo.call && !demo.call.ended && navigator.sendBeacon) {
      navigator.sendBeacon("/v1/demo-call/" + demo.token + "/turn", new Blob([JSON.stringify({ hangup: true })], { type: "application/json" }));
    }
  });

  function startCountdown(seconds) {
    var end = Date.now() + seconds * 1000;
    $("countdown").hidden = false; $("countdown-label").textContent = t("countdown");
    function tick() {
      var left = Math.max(0, Math.round((end - Date.now()) / 1000));
      $("countdown-time").textContent = Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0");
      if (!left) { stopCountdown(); $("countdown").hidden = true; $("confirm-title").textContent = t("calling"); $("confirm-sub").textContent = t("callingSub"); }
    }
    tick(); countdownTimer = setInterval(tick, 250);
  }
  function stopCountdown() { if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; } }

  // ---------------------------------------------------------------- events
  form.addEventListener("change", function (e) {
    var n = e.target.name;
    if (n === "lang") { lang = e.target.value; loadConfig(true); }
    if (n === "treatment") $("other-wrap").hidden = e.target.value !== "other";
    if (n === "pref") { $("schedule-wrap").hidden = e.target.value !== "scheduled"; setError("scheduled_at"); updateSubmit(); }
    if (e.target.id === "clinic") { if (e.target.value) setError("clinic"); $("consent").checked = false; $("wording-changed").hidden = true; render(); }
    if (e.target.id === "sched-day") buildTimes();
    if (e.target.id === "consent") { $("wording-changed").hidden = true; updateSubmit(); }
  });
  $("name").addEventListener("input", function () { if (this.value.trim()) setError("name"); });
  $("mobile").addEventListener("blur", function () {
    var m = normaliseMobile(this.value);
    if (/^[6-9]\d{9}$/.test(m)) { this.value = m.slice(0, 5) + " " + m.slice(5); setError("mobile"); }
  });
  $("restart").addEventListener("click", function () {
    stopCountdown(); demoStop(); form.reset(); lang = "en"; token = newToken();
    $("other-wrap").hidden = true; $("schedule-wrap").hidden = true; ["name", "mobile", "clinic"].forEach(function (f) { setError(f); });
    $("confirm-view").hidden = true; $("form-view").hidden = false; loadConfig(false);
  });

  render();
  loadConfig(false);
})();
