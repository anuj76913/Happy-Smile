// Fictional leads for the front-desk prototype. All names and numbers are made up.
// Times are minutes before the demo clock starts (14:20 IST), so the screen always
// looks like an afternoon in the pilot clinics.
//
// status:  needs_you | booked | no_answer | standard
// arm:     assistant | control
// tags:    asked_person | pain_swelling | price_emi | clinical | couldnt_understand | whatsapp_reply

window.HS_LEADS = [
  // ---------------- Needs you (assistant handed over) ----------------
  {
    id: "L101", name: "Sunita Devi", phone: "+91 90000 10101", treatment: "Implants", clinic: "hillcrest",
    language: "Hindi", arm: "assistant", status: "needs_you", enquiredAgo: 9, firstReachedAgo: 7, handoverAgo: 6,
    tags: ["pain_swelling"],
    summary: [
      "Enquired about implants; reports swelling and pain in the lower left gum since yesterday.",
      "Assistant flagged it as urgent, gave safe-care advice and did not book.",
      "She was told the clinic team would call her within a few minutes."
    ],
    captured: { treatment: "Implants", slot: "As soon as possible", urgency: "Urgent: pain and swelling" },
    recordingSecs: 74,
    transcript: [
      ["Assistant", "Namaste Sunita ji, main HappySmile ki virtual assistant bol rahi hoon. Aapne abhi implants ke baare mein enquiry ki thi. Yeh call quality ke liye record ho rahi hai. Kya abhi baat kar sakte hain?"],
      ["Caller", "Haan boliye. Actually kal se neeche wale masoode mein soojan hai, aur dard bhi ho raha hai."],
      ["Assistant", "Yeh sunkar afsos hua. Main abhi hamari clinic team ko bata rahi hoon, woh kuch hi minute mein aapko call karenge. Agar soojan badhe ya saans lene mein dikkat ho, to turant nazdeeki emergency mein jaayein."]
    ]
  },
  {
    id: "L102", name: "Kavita Joshi", phone: "+91 90000 10102", treatment: "Braces / aligners", clinic: "lotus",
    language: "English", arm: "assistant", status: "needs_you", enquiredAgo: 32, firstReachedAgo: 23, handoverAgo: 17,
    tags: ["price_emi", "asked_person"],
    summary: [
      "Interested in clear aligners for her 16-year-old son; she is the contact.",
      "Asked about EMI options and total cost, then asked to speak to a person.",
      "Prefers a Saturday morning consultation."
    ],
    captured: { treatment: "Clear aligners (for son, 16)", slot: "Saturday morning", urgency: "Not urgent" },
    recordingSecs: 131,
    transcript: [
      ["Caller", "Before I book anything, what would the whole treatment cost? And do you have EMI?"],
      ["Assistant", "Our team can go through costs and payment options with you. I can also book a consultation first, if you like."],
      ["Caller", "I'd rather talk to someone at the clinic, please."],
      ["Assistant", "Of course. I've passed your details on, and someone from Lotus Square will call you within 15 minutes."]
    ]
  },
  {
    id: "L103", name: "Rohan Mehta", phone: "+91 90000 10103", treatment: "Braces / aligners", clinic: "riverside",
    language: "English", arm: "assistant", status: "needs_you", enquiredAgo: 18, firstReachedAgo: 16, handoverAgo: 13,
    tags: ["asked_person"],
    summary: [
      "Interested in braces; had a consultation at another clinic last year.",
      "Asked to speak to a person after the disclosure. No questions answered.",
      "Open to evening slots this week."
    ],
    captured: { treatment: "Braces", slot: "Weekday evening", urgency: "Not urgent" },
    recordingSecs: 48,
    transcript: [
      ["Assistant", "Hi Rohan, this is HappySmile's virtual assistant, calling about the braces enquiry you just made. This call is recorded for quality. Is now a good time?"],
      ["Caller", "Oh, it's a bot? Can I just talk to a person?"],
      ["Assistant", "Sure. I've asked our Riverside team to call you. That will be within 15 minutes."]
    ]
  },
  {
    id: "L104", name: "Farhan Qureshi", phone: "+91 90000 10104", treatment: "Implants", clinic: "lotus",
    language: "Hindi", arm: "assistant", status: "needs_you", enquiredAgo: 14, firstReachedAgo: 12, handoverAgo: 9,
    tags: ["price_emi"],
    summary: [
      "Enquiring for his father, 64, who is missing two lower teeth.",
      "Main question is price per implant and whether EMI is available.",
      "Would like a weekday morning appointment for his father."
    ],
    captured: { treatment: "Implants (for father, 64)", slot: "Weekday morning", urgency: "Not urgent" },
    recordingSecs: 96,
    transcript: [
      ["Caller", "Ek implant ka kitna kharcha aata hai? Aur EMI milega kya?"],
      ["Assistant", "Kharche aur EMI ki poori jaankari hamari clinic team degi. Main unse aapko call karwati hoon. Tab tak kya main aapke papa ke liye consultation book kar doon?"],
      ["Caller", "Pehle price pata chal jaaye, phir book karenge."]
    ]
  },
  {
    id: "L105", name: "Neha Iyer", phone: "+91 90000 10105", treatment: "Whitening", clinic: "riverside",
    language: "English", arm: "assistant", status: "needs_you", enquiredAgo: 8, firstReachedAgo: 6, handoverAgo: 4,
    tags: ["clinical"],
    summary: [
      "Interested in whitening before a family wedding next month.",
      "Asked whether whitening is safe while breastfeeding; the assistant did not advise.",
      "Happy to book once her question is answered."
    ],
    captured: { treatment: "Whitening", slot: "Next week, afternoon", urgency: "Not urgent" },
    recordingSecs: 88,
    transcript: [
      ["Caller", "Is whitening safe while I'm breastfeeding?"],
      ["Assistant", "That's a good question for the dentist, so I won't guess. I'll ask our Riverside team to call you, and they can also book your consultation."]
    ]
  },
  {
    id: "L106", name: "Imran Shaikh", phone: "+91 90000 10106", treatment: "Other", clinic: "hillcrest",
    language: "Hindi", arm: "assistant", status: "needs_you", enquiredAgo: 5, firstReachedAgo: 3, handoverAgo: 2,
    tags: ["couldnt_understand"],
    summary: [
      "Selected \"Other\" on the form; the reason for the enquiry is unclear.",
      "Noisy line; speech recognition confidence stayed low on two turns.",
      "Handed over before any questions were completed."
    ],
    captured: { treatment: "Unclear", slot: "Not captured", urgency: "Unknown" },
    recordingSecs: 57,
    transcript: [
      ["Caller", "Haan ji... [unclear] ...daant mein woh jo... [unclear]"],
      ["Assistant", "Maaf kijiye, awaaz saaf nahi aa rahi. Main hamari team se aapko call karwati hoon."]
    ]
  },
  {
    id: "L107", name: "Deepa Menon", phone: "+91 90000 10107", treatment: "Whitening", clinic: "riverside",
    language: "English", arm: "assistant", status: "needs_you", enquiredAgo: 150, firstReachedAgo: null, handoverAgo: 1,
    tags: ["whatsapp_reply"],
    summary: [
      "Not reached by phone after three attempts; the no-answer WhatsApp message was sent.",
      "She replied on WhatsApp asking for a call after 5 pm.",
      "No call recording for this lead."
    ],
    captured: { treatment: "Whitening", slot: "Today after 5 pm (from WhatsApp)", urgency: "Not urgent" },
    whatsappMessage: "Sorry, I was in meetings. Can someone call me after 5 pm today?",
    attempts: [["Call 1", "No answer", 149], ["Call 2", "No answer", 144], ["Call 3", "Busy", 24], ["WhatsApp", "Delivered, replied", 23]]
  },

  // ---------------- Booked by assistant ----------------
  {
    id: "L201", name: "Asha Verma", phone: "+91 90000 10201", treatment: "Braces / aligners", clinic: "riverside",
    language: "English", arm: "assistant", status: "booked", enquiredAgo: 46, firstReachedAgo: 44,
    booking: { dayOffset: 1, time: "6:30 pm", dentist: "Dr. Meera Rao", whatsapp: "read", review: "pending", by: "assistant" },
    summary: ["Adult braces enquiry; no pain reported.", "Booked a consultation for tomorrow evening.", "Confirmation read on WhatsApp."],
    captured: { treatment: "Braces", slot: "Tomorrow, 6:30 pm", urgency: "Not urgent" },
    recordingSecs: 162,
    transcript: [
      ["Assistant", "I have tomorrow at 6:30 pm or the day after at 7:00 pm with Dr. Meera Rao. Which works better?"],
      ["Caller", "Tomorrow at 6:30 is good."],
      ["Assistant", "Done. That's tomorrow at 6:30 pm at Riverside with Dr. Meera Rao. You'll get a WhatsApp confirmation now."]
    ]
  },
  {
    id: "L202", name: "Vikram Rao", phone: "+91 90000 10202", treatment: "Implants", clinic: "hillcrest",
    language: "English", arm: "assistant", status: "booked", enquiredAgo: 95, firstReachedAgo: 93,
    booking: { dayOffset: 2, time: "11:00 am", dentist: "Dr. Karan Bhatia", whatsapp: "delivered", review: "approved", by: "assistant" },
    summary: ["Missing upper molar; wants to discuss an implant.", "Booked a consultation in two days.", "Booking reviewed and approved by front desk."],
    captured: { treatment: "Implant", slot: "In 2 days, 11:00 am", urgency: "Not urgent" },
    recordingSecs: 140,
    transcript: [
      ["Caller", "Morning is better for me, I work evenings."],
      ["Assistant", "I can do 11:00 am with Dr. Karan Bhatia at Hillcrest. Shall I book it?"],
      ["Caller", "Yes please."]
    ]
  },
  {
    id: "L203", name: "Meera Kulkarni", phone: "+91 90000 10203", treatment: "Whitening", clinic: "lotus",
    language: "English", arm: "assistant", status: "booked", enquiredAgo: 38, firstReachedAgo: 36,
    booking: { dayOffset: 0, time: "5:30 pm", dentist: "Dr. Leena Das", whatsapp: "read", review: "pending", by: "assistant" },
    summary: ["Whitening enquiry; wants it done this week.", "Booked a consultation for today at 5:30 pm.", "Review before the appointment today."],
    captured: { treatment: "Whitening", slot: "Today, 5:30 pm", urgency: "Not urgent" },
    recordingSecs: 118,
    transcript: [
      ["Caller", "Is there anything today itself?"],
      ["Assistant", "Yes, today at 5:30 pm with Dr. Leena Das at Lotus Square."],
      ["Caller", "Perfect, book it."]
    ]
  },
  {
    id: "L204", name: "Arjun Nair", phone: "+91 90000 10204", treatment: "Braces / aligners", clinic: "riverside",
    language: "English", arm: "assistant", status: "booked", enquiredAgo: 70, firstReachedAgo: 62,
    booking: { dayOffset: 3, time: "10:30 am", dentist: "Dr. Nisha Pillai", whatsapp: "delivered", review: "pending", by: "assistant" },
    summary: ["Reached on the second attempt.", "Interested in aligners; booked a consultation in three days.", "No questions outside scope."],
    captured: { treatment: "Aligners", slot: "In 3 days, 10:30 am", urgency: "Not urgent" },
    recordingSecs: 151,
    transcript: [
      ["Assistant", "Sorry I missed you earlier. Is now a better time?"],
      ["Caller", "Yes, go ahead."]
    ]
  },
  {
    id: "L205", name: "Pooja Sinha", phone: "+91 90000 10205", treatment: "Braces / aligners", clinic: "hillcrest",
    language: "Hindi", arm: "assistant", status: "booked", enquiredAgo: 27, firstReachedAgo: 25,
    booking: { dayOffset: 5, time: "12:00 pm", dentist: "Dr. Karan Bhatia", whatsapp: "failed", review: "pending", by: "assistant" },
    summary: ["Aligners enquiry; booked an afternoon consultation next week.", "WhatsApp confirmation could not be delivered.", "Call her to confirm the booking."],
    captured: { treatment: "Aligners", slot: "Next week, afternoon", urgency: "Not urgent" },
    recordingSecs: 133,
    transcript: [
      ["Caller", "Agle hafte ho sakta hai? Dopahar mein?"],
      ["Assistant", "Ji, dopahar 12 baje Dr. Karan Bhatia ke saath slot hai, Hillcrest clinic mein. Book kar doon?"],
      ["Caller", "Haan, kar dijiye."]
    ]
  },
  {
    id: "L206", name: "Nikhil Bhatt", phone: "+91 90000 10206", treatment: "Implants", clinic: "lotus",
    language: "English", arm: "assistant", status: "booked", enquiredAgo: 120, firstReachedAgo: 118,
    booking: { dayOffset: 4, time: "4:00 pm", dentist: "Dr. Leena Das", whatsapp: "read", review: "approved", by: "assistant" },
    summary: ["Implant enquiry after an extraction last month.", "Booked a consultation in four days.", "Reviewed and approved."],
    captured: { treatment: "Implant", slot: "In 4 days, 4:00 pm", urgency: "Not urgent" },
    recordingSecs: 125,
    transcript: [["Assistant", "That's booked: 4:00 pm with Dr. Leena Das at Lotus Square."]]
  },
  {
    id: "L207", name: "Swati Chauhan", phone: "+91 90000 10207", treatment: "Whitening", clinic: "riverside",
    language: "Hindi", arm: "assistant", status: "booked", enquiredAgo: 22, firstReachedAgo: 20,
    booking: { dayOffset: 1, time: "7:00 pm", dentist: "Dr. Meera Rao", whatsapp: "sent", review: "pending", by: "assistant" },
    summary: ["Whitening enquiry; prefers evenings after work.", "Booked tomorrow at 7:00 pm.", "Confirmation sent, not yet delivered."],
    captured: { treatment: "Whitening", slot: "Tomorrow, 7:00 pm", urgency: "Not urgent" },
    recordingSecs: 109,
    transcript: [
      ["Caller", "Kal shaam ko saat baje ho jayega?"],
      ["Assistant", "Ji, kal, shaam 7 baje, Dr. Meera Rao ke saath, Riverside clinic mein. Confirm kar doon?"],
      ["Caller", "Haan ji."]
    ]
  },

  // ---------------- No answer ----------------
  {
    id: "L301", name: "Rahul Bansal", phone: "+91 90000 10301", treatment: "Braces / aligners", clinic: "riverside",
    language: "English", arm: "assistant", status: "no_answer", enquiredAgo: 4, firstReachedAgo: null,
    attempts: [["Call 1", "No answer", 3]], nextRetryIn: 2
  },
  {
    id: "L302", name: "Anjali Kapoor", phone: "+91 90000 10302", treatment: "Implants", clinic: "hillcrest",
    language: "Hindi", arm: "assistant", status: "no_answer", enquiredAgo: 35, firstReachedAgo: null,
    attempts: [["Call 1", "No answer", 34], ["Call 2", "Busy", 29]], nextRetryIn: 91
  },
  {
    id: "L303", name: "Mohit Arora", phone: "+91 90000 10303", treatment: "Whitening", clinic: "lotus",
    language: "English", arm: "assistant", status: "no_answer", enquiredAgo: 170, firstReachedAgo: null,
    attempts: [["Call 1", "No answer", 169], ["Call 2", "No answer", 164], ["Call 3", "Voicemail", 44], ["WhatsApp", "Delivered", 44]],
    nextRetryIn: null
  },
  {
    id: "L304", name: "Fatima Begum", phone: "+91 90000 10304", treatment: "Braces / aligners", clinic: "hillcrest",
    language: "Hindi", arm: "assistant", status: "no_answer", enquiredAgo: 200, firstReachedAgo: null,
    attempts: [["Call 1", "No answer", 199], ["Call 2", "No answer", 194], ["Call 3", "No answer", 74], ["WhatsApp", "Read", 60]],
    nextRetryIn: null
  },

  // ---------------- Standard callback (control group) ----------------
  { id: "L401", name: "Gaurav Singh", phone: "+91 90000 10401", treatment: "Braces / aligners", clinic: "riverside", language: "English", arm: "control", status: "standard", enquiredAgo: 12, firstReachedAgo: null, outcome: "not_called" },
  { id: "L402", name: "Ritu Malhotra", phone: "+91 90000 10402", treatment: "Whitening", clinic: "hillcrest", language: "English", arm: "control", status: "standard", enquiredAgo: 25, firstReachedAgo: null, outcome: "not_called" },
  { id: "L403", name: "Harish Kumar", phone: "+91 90000 10403", treatment: "Implants", clinic: "lotus", language: "Hindi", arm: "control", status: "standard", enquiredAgo: 41, firstReachedAgo: null, outcome: "not_called" },
  { id: "L404", name: "Shalini Dutta", phone: "+91 90000 10404", treatment: "Braces / aligners", clinic: "riverside", language: "English", arm: "control", status: "standard", enquiredAgo: 58, firstReachedAgo: null, outcome: "no_answer" },
  { id: "L405", name: "Varun Khanna", phone: "+91 90000 10405", treatment: "Implants", clinic: "hillcrest", language: "English", arm: "control", status: "standard", enquiredAgo: 80, firstReachedAgo: 30, outcome: "booked" },
  { id: "L406", name: "Lakshmi Subramaniam", phone: "+91 90000 10406", treatment: "Whitening", clinic: "lotus", language: "English", arm: "control", status: "standard", enquiredAgo: 110, firstReachedAgo: 60, outcome: "not_interested" },
  { id: "L407", name: "Ayesha Siddiqui", phone: "+91 90000 10407", treatment: "Braces / aligners", clinic: "riverside", language: "Hindi", arm: "control", status: "standard", enquiredAgo: 135, firstReachedAgo: 50, outcome: "booked" },
  { id: "L408", name: "Tarun Joshi", phone: "+91 90000 10408", treatment: "Other", clinic: "hillcrest", language: "English", arm: "control", status: "standard", enquiredAgo: 6, firstReachedAgo: null, outcome: "not_called" },
  { id: "L409", name: "Pallavi Reddy", phone: "+91 90000 10409", treatment: "Braces / aligners", clinic: "lotus", language: "English", arm: "control", status: "standard", enquiredAgo: 90, firstReachedAgo: null, outcome: "no_answer" },
  { id: "L410", name: "Manoj Yadav", phone: "+91 90000 10410", treatment: "Implants", clinic: "riverside", language: "Hindi", arm: "control", status: "standard", enquiredAgo: 160, firstReachedAgo: 100, outcome: "follow_up" }
];

window.HS_DENTISTS = {
  riverside: ["Dr. Meera Rao", "Dr. Nisha Pillai"],
  hillcrest: ["Dr. Karan Bhatia", "Dr. Sana Mirza"],
  lotus: ["Dr. Leena Das", "Dr. Vivek Menon"]
};
