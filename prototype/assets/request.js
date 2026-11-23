/* Screen 1 — Request a call. Prototype only: nothing is sent anywhere. */
(function () {
  "use strict";

  var CALLER = window.HS_CALLER_ID || "+91 90000 12345";
  var WINDOW_START = 9 * 60;          // 09:00
  var WINDOW_LAST_CALL = 20 * 60 + 45; // no new calls in the last 15 minutes (EC-TIME-02)
  var WINDOW_END = 21 * 60;

  // ---------------------------------------------------------------- strings
  var T = {
    en: {
      brandSub: "Dental clinics", protoTag: "Prototype",
      title: "Request a call",
      subtitle: "Tell us what you are interested in. We will call you back within minutes.",
      langLabel: "Language for the call", nameLabel: "Your name", mobileLabel: "Mobile number",
      mobileHint: "10-digit Indian mobile number",
      treatmentLabel: "What are you interested in?",
      tBraces: "Braces / aligners", tWhitening: "Whitening", tImplants: "Implants", tOther: "Other",
      otherLabel: "Tell us briefly", otherPlaceholder: "Tell us briefly (optional)",
      clinicLabel: "Nearest clinic", clinicPlaceholder: "Choose a clinic",
      prefLabel: "How should we contact you?",
      prefNow: "Call me now", prefNowSubDay: "In about 2 minutes",
      prefNowSubNight: "Calling hours are 9 am to 9 pm. We will call after 9 am tomorrow",
      prefLater: "Call me at a time I pick", prefLaterSub: "Between 9 am and 9 pm",
      prefWa: "WhatsApp me instead", prefWaSub: "No call. Our team replies on WhatsApp",
      dayLabel: "Day", timeLabel: "Time", today: "Today", tomorrow: "Tomorrow",
      consent: "I agree to a call from HappySmile's virtual assistant about this enquiry, and to WhatsApp updates about my appointment. The call may be recorded. I can ask it to stop at any time.",
      submit: "Request my call", submitWa: "Message me on WhatsApp", submitting: "Sending...",
      submitHint: "Tick the box above to continue.",
      nameRequired: "Please enter your name.",
      mobileInvalid: "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.",
      clinicRequired: "Please choose a clinic.",
      expectTitle: "What to expect", edit: "Edit my details", restart: "Start again",
      staffLink: "View as clinic staff",
      treatmentWord: { braces: "braces / aligners", whitening: "whitening", implants: "implants", other: "your enquiry" },
      tail: " It can book a consultation or connect you to our team. Say “talk to a person” at any time.",
      discNowDay: function (n) { return "HappySmile's virtual assistant will call you in about 2 minutes from " + n + "."; },
      discNowNight: function (n) { return "Our calling hours are 9 am to 9 pm, so HappySmile's virtual assistant will call you after 9 am tomorrow from " + n + "."; },
      discSched: function (n, w) { return "HappySmile's virtual assistant will call you " + w + " from " + n + ". We will send a WhatsApp reminder 10 minutes before."; },
      discWa: function (n) { return "We will message you on WhatsApp from " + n + ". Our team will reply there during clinic hours, 9 am to 9 pm. We will not call unless you ask us to."; },
      cNowTitle: "Your call is on its way",
      cNowSub: function (t, c) { return "We will call you about " + t + (c ? " at HappySmile " + c : "") + "."; },
      cCountdown: "until the call",
      cCallingTitle: "Calling you now",
      cCallingSub: "Please pick up. If you miss it, we will try again in 5 minutes.",
      cNightTitle: "We will call you after 9 am tomorrow",
      cNightSub: "Our calling hours are 9 am to 9 pm. We have sent a WhatsApp message to confirm your request.",
      cSchedTitle: function (w) { return "We will call you " + w; },
      cSchedSub: "We will send a WhatsApp reminder 10 minutes before.",
      cWaTitle: "Check WhatsApp",
      cWaSub: function (t, c) { return "We have sent you a message about " + t + (c ? " at HappySmile " + c : "") + "."; },
      callerFrom: "The call will come from", waFrom: "Message sent from",
      callerHint: "Save this number so you recognise the call.",
      waHint: "Reply there and our team will help you book.",
      expectCall: [
        "It will say it is HappySmile's virtual assistant.",
        "It can book a consultation for you, or ask our team to call you.",
        "Say “talk to a person” at any time.",
        "If you are in pain or have swelling, tell it. A team member will call you first."
      ],
      expectWa: [
        "Our team replies during clinic hours, 9 am to 9 pm.",
        "You can ask for a call at any time in the chat.",
        "Reply STOP to stop messages."
      ],
      when: function (dayIdx, dateObj, timeStr) {
        var d = dayIdx === 0 ? "today" : dayIdx === 1 ? "tomorrow" : "on " + dateObj.toLocaleDateString("en-IN", { weekday: "long" });
        return d + " at " + timeStr;
      }
    },
    hi: {
      brandSub: "डेंटल क्लिनिक", protoTag: "प्रोटोटाइप",
      title: "कॉल का अनुरोध करें",
      subtitle: "बताइए आप किसमें रुचि रखते हैं। हम कुछ ही मिनटों में आपको कॉल करेंगे।",
      langLabel: "कॉल की भाषा", nameLabel: "आपका नाम", mobileLabel: "मोबाइल नंबर",
      mobileHint: "10 अंकों का भारतीय मोबाइल नंबर",
      treatmentLabel: "आप किसमें रुचि रखते हैं?",
      tBraces: "ब्रेसेस / अलाइनर", tWhitening: "दाँतों की सफ़ेदी", tImplants: "इम्प्लांट", tOther: "अन्य",
      otherLabel: "संक्षेप में बताइए", otherPlaceholder: "संक्षेप में बताइए (वैकल्पिक)",
      clinicLabel: "नज़दीकी क्लिनिक", clinicPlaceholder: "क्लिनिक चुनें",
      prefLabel: "हम आपसे कैसे संपर्क करें?",
      prefNow: "मुझे अभी कॉल करें", prefNowSubDay: "लगभग 2 मिनट में",
      prefNowSubNight: "कॉल का समय सुबह 9 से रात 9 बजे तक है। हम कल सुबह 9 बजे के बाद कॉल करेंगे",
      prefLater: "मेरे चुने समय पर कॉल करें", prefLaterSub: "सुबह 9 से रात 9 बजे के बीच",
      prefWa: "कॉल के बजाय WhatsApp करें", prefWaSub: "कोई कॉल नहीं। हमारी टीम WhatsApp पर जवाब देगी",
      dayLabel: "दिन", timeLabel: "समय", today: "आज", tomorrow: "कल",
      consent: "मैं इस पूछताछ के बारे में HappySmile की वर्चुअल असिस्टेंट से कॉल और अपनी अपॉइंटमेंट के बारे में WhatsApp अपडेट पाने के लिए सहमत हूँ। कॉल रिकॉर्ड की जा सकती है। मैं किसी भी समय इसे रोकने के लिए कह सकता/सकती हूँ।",
      submit: "मेरी कॉल का अनुरोध करें", submitWa: "मुझे WhatsApp पर मैसेज करें", submitting: "भेजा जा रहा है...",
      submitHint: "आगे बढ़ने के लिए ऊपर दिए बॉक्स पर टिक करें।",
      nameRequired: "कृपया अपना नाम लिखें।",
      mobileInvalid: "6, 7, 8 या 9 से शुरू होने वाला 10 अंकों का मोबाइल नंबर लिखें।",
      clinicRequired: "कृपया एक क्लिनिक चुनें।",
      expectTitle: "आगे क्या होगा", edit: "अपनी जानकारी बदलें", restart: "फिर से शुरू करें",
      staffLink: "क्लिनिक स्टाफ़ का दृश्य देखें",
      treatmentWord: { braces: "ब्रेसेस / अलाइनर", whitening: "दाँतों की सफ़ेदी", implants: "इम्प्लांट", other: "आपकी पूछताछ" },
      tail: " वह आपकी कंसल्टेशन बुक कर सकती है या आपको हमारी टीम से जोड़ सकती है। किसी भी समय “किसी इंसान से बात करनी है” कहें।",
      discNowDay: function (n) { return "HappySmile की वर्चुअल असिस्टेंट लगभग 2 मिनट में " + n + " से आपको कॉल करेगी।"; },
      discNowNight: function (n) { return "हमारे कॉल का समय सुबह 9 से रात 9 बजे तक है, इसलिए HappySmile की वर्चुअल असिस्टेंट कल सुबह 9 बजे के बाद " + n + " से आपको कॉल करेगी।"; },
      discSched: function (n, w) { return "HappySmile की वर्चुअल असिस्टेंट " + w + " " + n + " से आपको कॉल करेगी। कॉल से 10 मिनट पहले हम WhatsApp पर याद दिलाएँगे।"; },
      discWa: function (n) { return "हम " + n + " से आपको WhatsApp पर मैसेज करेंगे। हमारी टीम क्लिनिक के समय (सुबह 9 से रात 9 बजे) में वहीं जवाब देगी। जब तक आप न कहें, हम कॉल नहीं करेंगे।"; },
      cNowTitle: "आपकी कॉल आ रही है",
      cNowSub: function (t, c) { return (c ? "HappySmile " + c + " से " : "") + t + " के बारे में आपको कॉल आएगी।"; },
      cCountdown: "कॉल आने में",
      cCallingTitle: "अभी आपको कॉल कर रहे हैं",
      cCallingSub: "कृपया कॉल उठाएँ। अगर छूट जाए, तो हम 5 मिनट बाद फिर कोशिश करेंगे।",
      cNightTitle: "हम कल सुबह 9 बजे के बाद आपको कॉल करेंगे",
      cNightSub: "हमारे कॉल का समय सुबह 9 से रात 9 बजे तक है। आपके अनुरोध की पुष्टि के लिए हमने WhatsApp पर मैसेज भेजा है।",
      cSchedTitle: function (w) { return "हम आपको " + w + " कॉल करेंगे"; },
      cSchedSub: "कॉल से 10 मिनट पहले हम WhatsApp पर याद दिलाएँगे।",
      cWaTitle: "WhatsApp देखें",
      cWaSub: function (t, c) { return "हमने आपको " + (c ? "HappySmile " + c + " में " : "") + t + " के बारे में मैसेज भेजा है।"; },
      callerFrom: "कॉल इस नंबर से आएगी", waFrom: "मैसेज इस नंबर से भेजा गया",
      callerHint: "यह नंबर सेव कर लें ताकि आप कॉल पहचान सकें।",
      waHint: "वहीं जवाब दें, हमारी टीम बुकिंग में मदद करेगी।",
      expectCall: [
        "वह बताएगी कि वह HappySmile की वर्चुअल असिस्टेंट है।",
        "वह आपकी कंसल्टेशन बुक कर सकती है या हमारी टीम से आपको कॉल करवा सकती है।",
        "किसी भी समय “किसी इंसान से बात करनी है” कहें।",
        "अगर दर्द या सूजन है, तो बताएँ। हमारी टीम का सदस्य पहले आपको कॉल करेगा।"
      ],
      expectWa: [
        "हमारी टीम क्लिनिक के समय, सुबह 9 से रात 9 बजे तक, जवाब देती है।",
        "चैट में आप कभी भी कॉल के लिए कह सकते हैं।",
        "मैसेज बंद करने के लिए STOP लिखें।"
      ],
      when: function (dayIdx, dateObj, timeStr, mins) {
        var days = ["रविवार", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"];
        var d = dayIdx === 0 ? "आज" : dayIdx === 1 ? "कल" : days[dateObj.getDay()] + " को";
        var part = mins < 12 * 60 ? "सुबह" : mins < 16 * 60 ? "दोपहर" : mins < 19 * 60 ? "शाम" : "रात";
        return d + " " + part + " " + timeStr.replace(/\s?(am|pm)$/i, "") + " बजे";
      }
    }
  };

  // ---------------------------------------------------------------- state
  var $ = function (id) { return document.getElementById(id); };
  var form = $("request-form");
  var lang = "en";
  var clockMode = "day";
  var clockBase = demoBase("day");
  var loadedAt = Date.now();
  var countdownTimer = null;
  var submitting = false;

  function demoBase(mode) {
    var d = new Date();
    if (mode === "night") d.setHours(23, 30, 0, 0); else d.setHours(14, 20, 0, 0);
    return d;
  }
  function now() { return new Date(clockBase.getTime() + (Date.now() - loadedAt)); }
  function minutesOfDay(d) { return d.getHours() * 60 + d.getMinutes(); }
  function canCallNow() { var m = minutesOfDay(now()); return m >= WINDOW_START && m <= WINDOW_LAST_CALL; }
  function t(key) { return T[lang][key]; }
  function checked(name) { var el = form.querySelector('input[name="' + name + '"]:checked'); return el ? el.value : null; }

  function fmtTime(mins) {
    var h = Math.floor(mins / 60), m = mins % 60;
    var suffix = h >= 12 ? "pm" : "am";
    var h12 = h % 12 === 0 ? 12 : h % 12;
    return h12 + ":" + (m < 10 ? "0" : "") + m + " " + suffix;
  }

  // ---------------------------------------------------------------- render
  function applyStrings() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var v = t(el.getAttribute("data-i18n"));
      if (typeof v === "string") el.textContent = v;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
    });
    updateSubmitLabel();
    $("pref-now-sub").textContent = canCallNow() ? t("prefNowSubDay") : t("prefNowSubNight");
    buildScheduleOptions(true);
    renderDisclosure();
    revalidateShownErrors();
  }

  function fillClinics() {
    var sel = $("clinic");
    (window.HS_CLINICS || []).forEach(function (c) {
      var o = document.createElement("option");
      o.value = c.id; o.textContent = c.name;
      sel.appendChild(o);
    });
  }

  function buildScheduleOptions(keepSelection) {
    var daySel = $("sched-day"), timeSel = $("sched-time");
    var prevDay = keepSelection ? daySel.value : "", prevTime = keepSelection ? timeSel.value : "";
    var n = now(), nm = minutesOfDay(n);
    var firstToday = Math.ceil((nm + 30) / 30) * 30;

    daySel.innerHTML = "";
    for (var i = 0; i < 7; i++) {
      if (i === 0 && firstToday > 20 * 60 + 30) continue; // no slots left today
      var d = new Date(n); d.setDate(d.getDate() + i);
      var label = i === 0 ? t("today") : i === 1 ? t("tomorrow")
        : d.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { weekday: "short", day: "numeric", month: "short" });
      var o = document.createElement("option");
      o.value = String(i); o.textContent = label;
      daySel.appendChild(o);
    }
    if (prevDay && daySel.querySelector('option[value="' + prevDay + '"]')) daySel.value = prevDay;
    buildTimes(prevTime);
  }

  function buildTimes(prevTime) {
    var daySel = $("sched-day"), timeSel = $("sched-time");
    var nm = minutesOfDay(now());
    var start = daySel.value === "0" ? Math.max(WINDOW_START, Math.ceil((nm + 30) / 30) * 30) : WINDOW_START;
    timeSel.innerHTML = "";
    for (var m = start; m <= 20 * 60 + 30; m += 30) {
      var o = document.createElement("option");
      o.value = String(m); o.textContent = fmtTime(m);
      timeSel.appendChild(o);
    }
    if (prevTime && timeSel.querySelector('option[value="' + prevTime + '"]')) timeSel.value = prevTime;
    else if (daySel.value !== "0") timeSel.value = String(18 * 60); // sensible default: 6 pm
  }

  function scheduledWhen() {
    var dayIdx = parseInt($("sched-day").value, 10);
    var mins = parseInt($("sched-time").value, 10);
    var d = new Date(now()); d.setDate(d.getDate() + dayIdx);
    return T[lang].when(dayIdx, d, fmtTime(mins), mins);
  }

  function renderDisclosure() {
    var pref = checked("pref");
    var box = $("disclosure");
    var text;
    if (pref === "whatsapp") text = T[lang].discWa(CALLER);
    else if (pref === "scheduled") text = T[lang].discSched(CALLER, scheduledWhen()) + t("tail");
    else text = (canCallNow() ? T[lang].discNowDay(CALLER) : T[lang].discNowNight(CALLER)) + t("tail");

    // Bold the calling number so people notice it.
    box.textContent = "";
    var parts = text.split(CALLER);
    parts.forEach(function (p, i) {
      box.appendChild(document.createTextNode(p));
      if (i < parts.length - 1) { var s = document.createElement("strong"); s.textContent = CALLER; box.appendChild(s); }
    });
  }

  function updateSubmitLabel() {
    var btn = $("submit");
    if (submitting) { btn.textContent = t("submitting"); return; }
    btn.textContent = checked("pref") === "whatsapp" ? t("submitWa") : t("submit");
  }

  function updateSubmitState() {
    var ok = $("consent").checked;
    $("submit").disabled = !ok || submitting;
    $("submit-hint").hidden = ok;
  }

  // ---------------------------------------------------------------- validation
  function normaliseMobile(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    if (digits.length === 12 && digits.indexOf("91") === 0) digits = digits.slice(2);
    else if (digits.length === 11 && digits.charAt(0) === "0") digits = digits.slice(1);
    return digits;
  }

  function setError(field, msgKey) {
    var input = $(field), err = $(field + "-error");
    if (msgKey) { input.setAttribute("aria-invalid", "true"); err.textContent = t(msgKey); err.hidden = false; err.dataset.key = msgKey; }
    else { input.removeAttribute("aria-invalid"); err.hidden = true; err.textContent = ""; delete err.dataset.key; }
  }

  function validate() {
    var okName = $("name").value.trim().length > 0;
    var mob = normaliseMobile($("mobile").value);
    var okMobile = /^[6-9]\d{9}$/.test(mob);
    var okClinic = !!$("clinic").value;
    setError("name", okName ? null : "nameRequired");
    setError("mobile", okMobile ? null : "mobileInvalid");
    setError("clinic", okClinic ? null : "clinicRequired");
    if (!okName) $("name").focus(); else if (!okMobile) $("mobile").focus(); else if (!okClinic) $("clinic").focus();
    return okName && okMobile && okClinic;
  }

  function revalidateShownErrors() {
    ["name", "mobile", "clinic"].forEach(function (f) {
      var err = $(f + "-error");
      if (!err.hidden && err.dataset.key) err.textContent = t(err.dataset.key);
    });
  }

  // ---------------------------------------------------------------- confirmation
  function showConfirmation() {
    var pref = checked("pref");
    var tkey = checked("treatment");
    var tword = T[lang].treatmentWord[tkey];
    var clinic = ($("clinic").selectedOptions[0] || {}).textContent || "";
    var title = $("confirm-title"), sub = $("confirm-sub");
    var countdown = $("countdown");
    var expect = pref === "whatsapp" ? t("expectWa") : t("expectCall");

    $("caller-number").textContent = CALLER;
    $("caller-label").textContent = pref === "whatsapp" ? t("waFrom") : t("callerFrom");
    $("caller-hint").textContent = pref === "whatsapp" ? t("waHint") : t("callerHint");
    countdown.hidden = true;

    if (pref === "whatsapp") {
      title.textContent = t("cWaTitle");
      sub.textContent = T[lang].cWaSub(tword, clinic);
    } else if (pref === "scheduled") {
      title.textContent = T[lang].cSchedTitle(scheduledWhen());
      sub.textContent = t("cSchedSub");
    } else if (!canCallNow()) {
      title.textContent = t("cNightTitle");
      sub.textContent = t("cNightSub");
    } else {
      title.textContent = t("cNowTitle");
      sub.textContent = T[lang].cNowSub(tword, clinic);
      startCountdown(120);
    }

    var ul = $("expect");
    ul.innerHTML = "";
    expect.forEach(function (line) { var li = document.createElement("li"); li.textContent = line; ul.appendChild(li); });

    $("form-view").hidden = true;
    $("confirm-view").hidden = false;
    title.setAttribute("tabindex", "-1");
    title.focus();
    window.scrollTo(0, 0);
  }

  function startCountdown(seconds) {
    stopCountdown();
    var end = Date.now() + seconds * 1000;
    var box = $("countdown"), time = $("countdown-time"), label = $("countdown-label");
    box.hidden = false;
    label.textContent = t("cCountdown");
    function tick() {
      var left = Math.max(0, Math.round((end - Date.now()) / 1000));
      time.textContent = Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0");
      if (left === 0) {
        stopCountdown();
        box.hidden = true;
        $("confirm-title").textContent = t("cCallingTitle");
        $("confirm-sub").textContent = t("cCallingSub");
      }
    }
    tick();
    countdownTimer = setInterval(tick, 250);
  }
  function stopCountdown() { if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; } }

  function backToForm(reset) {
    stopCountdown();
    if (reset) {
      form.reset();
      ["name", "mobile", "clinic"].forEach(function (f) { setError(f, null); });
      lang = "en";
      $("other-wrap").hidden = true;
      $("schedule-wrap").hidden = true;
    }
    $("confirm-view").hidden = true;
    $("form-view").hidden = false;
    applyStrings();
    updateSubmitState();
    window.scrollTo(0, 0);
  }

  // ---------------------------------------------------------------- events
  form.addEventListener("change", function (e) {
    var n = e.target.name;
    if (n === "lang") { lang = e.target.value; applyStrings(); }
    if (n === "treatment") $("other-wrap").hidden = e.target.value !== "other";
    if (n === "pref") {
      $("schedule-wrap").hidden = e.target.value !== "scheduled";
      updateSubmitLabel();
      renderDisclosure();
    }
    if (e.target.id === "sched-day") { buildTimes(""); renderDisclosure(); }
    if (e.target.id === "sched-time") renderDisclosure();
    if (e.target.id === "consent") updateSubmitState();
    if (e.target.id === "clinic" && e.target.value) setError("clinic", null);
  });

  $("name").addEventListener("input", function () { if (this.value.trim()) setError("name", null); });
  $("mobile").addEventListener("blur", function () {
    var mob = normaliseMobile(this.value);
    if (/^[6-9]\d{9}$/.test(mob)) { this.value = mob.slice(0, 5) + " " + mob.slice(5); setError("mobile", null); }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (submitting || !$("consent").checked) return; // double-submit guard (EC-FORM-10)
    if (!validate()) return;
    submitting = true;
    updateSubmitLabel(); updateSubmitState();
    setTimeout(function () {
      submitting = false;
      updateSubmitLabel(); updateSubmitState();
      showConfirmation();
    }, 600);
  });

  $("edit").addEventListener("click", function () { backToForm(false); });
  $("restart").addEventListener("click", function () { backToForm(true); });

  document.querySelectorAll('input[name="clock"]').forEach(function (r) {
    r.addEventListener("change", function () {
      clockMode = this.value;
      clockBase = demoBase(clockMode);
      loadedAt = Date.now();
      if (!$("confirm-view").hidden) backToForm(false); else applyStrings();
    });
  });

  // ---------------------------------------------------------------- init
  fillClinics();
  applyStrings();
  updateSubmitState();
})();
