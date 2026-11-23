/* Shared browser voice loop (used by /voice and by the enquiry page's demo call).
   Chrome speech synthesis speaks the assistant's line, then Chrome speech recognition listens
   for the reply. Turn-taking is half-duplex, so the microphone never hears the assistant.

   var call = HSVoiceCall({
     turn: function (payload) { return Promise<{say, end, lang}> },  // payload: {text, confidence} | {silence} | {hangup}
     el: { dot, state, log, interim },                                // elements to draw into
     uiLang: "en",                                                    // optional: fixed UI language (default: follows the call)
     msgs: {...},                                                     // optional overrides of MSGS.en / MSGS.hi
     onReply: function (r) {},  onEnd: function (r) {},  onError: function (e) {},  onLang: function (lang) {}
   });
   call.start(firstLine, lang); call.typed(text); call.skip(); call.listenAgain(); call.hangup();
*/
(function () {
  "use strict";

  var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var synth = window.speechSynthesis;
  var LOCALE = { en: "en-IN", hi: "hi-IN" };
  var MSGS = {
    en: { you: "You", assistant: "Assistant", speaking: "Assistant is speaking…", listening: "Listening… speak now",
      thinking: "Thinking…", typeReply: "Type your reply below", silent: "(you stayed silent)", hungUp: "(you hung up)",
      micBlocked: "Microphone blocked. Allow it in the address bar, or type your replies.", micBlockedState: "Microphone blocked",
      network: "Speech recognition needs an internet connection (Chrome uses an online service). Type your replies instead.",
      ended: "Call ended", error: "Something went wrong: ", switched: function (l) { return "Language switched to " + (l === "hi" ? "Hindi" : "English"); } },
    hi: { you: "आप", assistant: "असिस्टेंट", speaking: "असिस्टेंट बोल रही है…", listening: "सुन रही है… अब बोलिए",
      thinking: "सोच रही है…", typeReply: "नीचे अपना जवाब लिखें", silent: "(आप चुप रहे)", hungUp: "(आपने कॉल काट दी)",
      micBlocked: "माइक्रोफ़ोन बंद है। एड्रेस बार में इसकी अनुमति दें, या जवाब लिखें।", micBlockedState: "माइक्रोफ़ोन बंद है",
      network: "बोलकर जवाब देने के लिए इंटरनेट चाहिए। कृपया जवाब लिखें।",
      ended: "कॉल समाप्त", error: "कुछ गड़बड़ हुई: ", switched: function (l) { return "भाषा बदली: " + (l === "hi" ? "हिन्दी" : "English"); } }
  };

  function pickVoice(locale) {
    var voices = synth ? synth.getVoices() : [];
    var exact = voices.filter(function (v) { return v.lang === locale; });
    var google = exact.filter(function (v) { return /google/i.test(v.name); });
    return google[0] || exact[0] || voices.filter(function (v) { return v.lang && v.lang.slice(0, 2) === locale.slice(0, 2); })[0] || null;
  }

  function HSVoiceCall(opts) {
    var el = opts.el;
    var c = { lang: "en", busy: false, ended: false, rec: null, heard: false, speakId: 0 };
    var noop = function () {};
    var onReply = opts.onReply || noop, onEnd = opts.onEnd || noop, onError = opts.onError || noop, onLang = opts.onLang || noop;

    function m(k) { var ui = opts.uiLang || c.lang, custom = opts.msgs && opts.msgs[ui]; return (custom && custom[k]) || MSGS[ui][k]; }
    function setState(kind, text) { if (el.dot) el.dot.className = "vdot " + kind; if (el.state) el.state.textContent = text; }
    function line(who, text) {
      var d = document.createElement("div");
      d.className = "vline " + who;
      if (who === "system") d.textContent = text;
      else {
        var w = document.createElement("span"); w.className = "who"; w.textContent = who === "assistant" ? m("assistant") : m("you");
        d.appendChild(w); d.appendChild(document.createTextNode(text));
      }
      el.log.appendChild(d); el.log.scrollTop = el.log.scrollHeight;
    }
    function setLang(lang) { c.lang = lang === "hi" ? "hi" : "en"; onLang(c.lang); }

    // ---------------------------------------------------------------- speaking
    function speak(text, then) {
      if (!synth || !text) { then(); return; }
      synth.cancel();
      var id = ++c.speakId;
      var u = new SpeechSynthesisUtterance(text);
      u.lang = LOCALE[c.lang];
      var v = pickVoice(u.lang); if (v) u.voice = v;
      u.rate = c.lang === "hi" ? 0.95 : 1.0;
      var done = false;
      var finish = function () { if (!done && id === c.speakId) { done = true; then(); } };
      u.onend = finish; u.onerror = finish;
      setState("speaking", m("speaking"));
      synth.speak(u);
      // Some browsers never fire onend for long utterances; don't get stuck.
      setTimeout(function () { if (!done && !synth.speaking) finish(); }, 1500 + text.length * 90);
    }

    // ---------------------------------------------------------------- listening
    function listen() {
      if (c.ended) return;
      if (!Recognition) { setState("", m("typeReply")); return; }
      stopListening();
      var rec = new Recognition();
      rec.lang = LOCALE[c.lang];
      rec.interimResults = true;
      rec.continuous = false;
      rec.maxAlternatives = 1;
      c.rec = rec; c.heard = false;
      rec.onresult = function (e) {
        var interim = "", final = null, conf = 0.9;
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var r = e.results[i];
          if (r.isFinal) { final = r[0].transcript; conf = r[0].confidence || 0.9; } else interim += r[0].transcript;
        }
        if (el.interim) el.interim.textContent = interim;
        if (final !== null && !c.heard) { c.heard = true; if (el.interim) el.interim.textContent = ""; send({ text: final.trim(), confidence: conf }, final.trim()); }
      };
      rec.onerror = function (e) {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          c.heard = true; line("system", m("micBlocked")); setState("", m("micBlockedState"));
        } else if (e.error === "network") {
          c.heard = true; line("system", m("network")); setState("", m("typeReply"));
        }
      };
      rec.onend = function () {
        if (c.rec === rec) c.rec = null;
        if (c.heard || c.ended || c.busy) return;
        send({ silence: true }, null);  // nothing said: that's silence, like on a real call
      };
      try { rec.start(); setState("listening", m("listening")); } catch (err) { /* already started */ }
    }
    function stopListening() {
      if (c.rec) { var r = c.rec; c.rec = null; c.heard = true; try { r.abort(); } catch (e) { /* ignore */ } }
    }

    // ---------------------------------------------------------------- turns
    function send(payload, shown) {
      if (c.busy || c.ended) return;
      c.busy = true;
      if (shown) line("caller", shown);
      else if (payload.silence) line("system", m("silent"));
      else if (payload.hangup) line("system", m("hungUp"));
      setState("thinking", m("thinking"));
      opts.turn(payload).then(function (r) {
        c.busy = false;
        if (r.lang && r.lang !== c.lang) { setLang(r.lang); line("system", m("switched")(r.lang)); }
        onReply(r, line);
        if (r.say) line("assistant", r.say);
        if (r.end) {
          c.ended = true; stopListening();
          speak(r.say, function () { setState("", m("ended")); });
          onEnd(r);
          return;
        }
        speak(r.say, listen);
      }).catch(function (e) {
        c.busy = false;
        setState("", m("error") + (e.message || ""));
        onError(e, line);
      });
    }

    if (synth) synth.getVoices();  // voices load asynchronously; warm them up

    return {
      supported: !!Recognition,
      start: function (say, lang) {
        c = { lang: "en", busy: false, ended: false, rec: null, heard: false, speakId: c.speakId };
        setLang(lang); el.log.innerHTML = ""; if (el.interim) el.interim.textContent = "";
        if (say) line("assistant", say);
        speak(say, listen);
      },
      typed: function (text) { if (synth) synth.cancel(); stopListening(); send({ text: text }, text); },
      skip: function () { if (synth) synth.cancel(); },
      listenAgain: function () { if (synth) synth.cancel(); listen(); },
      hangup: function () { if (synth) synth.cancel(); stopListening(); send({ hangup: true }, null); },
      stop: function () { c.ended = true; c.speakId++; if (synth) synth.cancel(); stopListening(); },
      line: line,
      get lang() { return c.lang; },
      get ended() { return c.ended; }
    };
  }

  window.HSVoiceCall = HSVoiceCall;
})();
