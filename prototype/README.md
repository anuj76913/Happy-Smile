# HappySmile prototype — two clickable screens

Phase 1 of [implementation-plan.md](../docs/implementation-plan.md#5-phase-1--clickable-prototype-and-case-submission); design in [architecture.md §19](../docs/architecture.md#19-prototype-mockup-architecture).

| Screen | File | Width | Scenario |
|---|---|---|---|
| 1. Request a call | `index.html` | ~390 px (mobile) | The moment a person asks to be contacted |
| 2. Leads | `leads.html` | ~1280 px (desktop) | What HappySmile's front desk sees afterwards |

Static HTML, CSS and JavaScript. No build step, no backend, no external requests, no API keys. All names, numbers and clinics are fictional.

## Run locally

Open `index.html` in a browser. Data lives in `data/*.js` rather than `.json`, so the pages also work from `file://` (browsers block `fetch()` there).

## Deploy (public URL, no login)

Any static host works. Pick one:

**GitHub Pages**
```bash
cd prototype
git init && git add . && git commit -m "HappySmile prototype"
gh repo create happysmile-prototype --public --source . --push
gh api -X POST repos/{owner}/happysmile-prototype/pages -f "source[branch]=main" -f "source[path]=/"
# URL: https://<your-username>.github.io/happysmile-prototype/
```

**Netlify Drop:** drag the `prototype` folder onto https://app.netlify.com/drop.

**Vercel:** `npx vercel deploy --prod` from inside `prototype/`.

Then open the URL in a **private window** to confirm it loads without a login (P1-06).

## What you can try

**Screen 1**
- Submit is disabled until the consent box is ticked; the hint explains why.
- Submit with empty fields to see the inline errors.
- Mobile numbers are cleaned up: `+91 98765-43210` and `098765 43210` both work; `12345` doesn't.
- Switch the call language to Hindi: labels, disclosure and consent all change, and typed values are kept.
- "Call me now" leads to a confirmation with the calling number and a 2:00 countdown, then "Calling you now".
- "Call me at a time I pick" shows a day and time picker within calling hours; the disclosure names the chosen time.
- "WhatsApp me instead" changes the button and the confirmation.
- **Prototype preview time → Night 23:30**: the form stops promising "2 minutes" and says the call comes after 9 am tomorrow (edge case EC-TIME-01).

**Screen 2**
- Top strip and tab counts come from the same data and stay in sync as you act.
- **Needs you**: urgent first, then longest wait; live timers against 5- and 15-minute targets, each with a text label as well as a colour.
- Click a lead: details, AI summary, captured answers, transcript (including Hinglish), and a simulated recording player.
- **Call now** marks the lead as picked up; **Book slot** opens a slot picker and sends the lead out of the queue; **Mark not interested** has Undo.
- "Was this handover right?": thumbs down asks what was wrong.
- **Booked by assistant**: **Review** opens Approve / Change time / Cancel (a reason is required to cancel). One booking shows a WhatsApp delivery failure.
- **No answer**: attempt history; the first lead's retry fires live after about 2 minutes.
- **Standard callback**: the pilot control group, with outcomes recorded by staff.
- Clinic filter; Escape closes the panel; arrow keys move between tabs. Below 1100 px the panel becomes an overlay.

## Review checklist (P1-07)

| Check | Result |
|---|---|
| No lorem ipsum, no emoji | Scanned: none |
| Only fictional phone numbers (`+91 90000 …`) | Scanned: none outside that range |
| No real branding (logo, colours of any real clinic) | Text wordmark only |
| No horizontal scroll at 320, 390, 1024, 1280 px | Checked in headless Chrome |
| No JavaScript errors across 17 scripted states | Checked |
| Keyboard: tabs, rows (name buttons), panel actions, dialogs | Real buttons and native dialogs |
| Opens without login | Check after deploying |

## Files

```
prototype/
  index.html          Screen 1
  leads.html          Screen 2
  assets/styles.css   shared tokens and components
  assets/request.css  Screen 1 layout
  assets/request.js   Screen 1 behaviour (EN/HI strings, validation, confirmation)
  assets/leads.css    Screen 2 layout
  assets/leads.js     Screen 2 behaviour (strip, tabs, panel, dialogs, timers)
  data/clinics.js     fictional clinics and calling number
  data/leads.js       28 fictional leads across all four tabs
```
