import { Portrait } from "/static/face.js";

const app = document.querySelector("#app");
const clientId = localStorage.getItem("lingocoach.client") || crypto.randomUUID();
localStorage.setItem("lingocoach.client", clientId);

const saved = JSON.parse(localStorage.getItem("lingocoach.settings.v3") || "null");
const settings = Object.assign({
  track: "ielts",
  partner: "amelia",
  target: "yue",
  support: "en",
  level: "beginner",
  script: "Hant",
  accent: "en-GB",
  pinyin_tone: "mark",
  autoplay: true,
  target_band: 6.5,
  module: "academic",
}, saved);

let boot = null;
let portrait = null;
let mode = "idle";
let visemeTimer = 0;
let session = null;

function save() {
  localStorage.setItem("lingocoach.settings.v3", JSON.stringify(settings));
}

function partner() {
  return boot.partners.find((row) => row.id === settings.partner) || boot.partners[0];
}

function title(row) {
  return row.title[settings.support] || row.title.en;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Client-Id": clientId },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "coach_unavailable");
    error.status = response.status;
    throw error;
  }
  return data;
}

function voiceFor(lang, gender) {
  const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  const want = lang === "yue" ? ["zh-HK", "yue"] : lang === "cmn" ? ["zh-CN"] : [settings.accent];
  if (lang === "yue") {
    const bad = (voice) => /zh-CN|zh-TW|cmn/i.test(`${voice.lang} ${voice.name}`);
    const pool = voices.filter((voice) => !bad(voice) && want.some((code) => voice.lang.toLowerCase().includes(code.toLowerCase().slice(0, 5))));
    const gendered = pool.find((voice) => gender === "woman" ? /female|woman|samantha|ting/i.test(voice.name) : /male|man|daniel/i.test(voice.name));
    return gendered || pool[0] || null;
  }
  const pool = voices.filter((voice) => want.some((code) => voice.lang.toLowerCase().startsWith(code.toLowerCase().slice(0, 2)) || voice.lang.toLowerCase().includes(code.toLowerCase())));
  const gendered = pool.find((voice) => gender === "woman" ? /female|woman|samantha|karen/i.test(voice.name) : /male|man|daniel|rishi/i.test(voice.name));
  return gendered || pool[0] || voices.find((voice) => voice.lang.toLowerCase().startsWith(want[0].slice(0, 2))) || null;
}

function speak(text, lang, visemes) {
  window.speechSynthesis?.cancel();
  clearInterval(visemeTimer);
  const person = partner();
  const voice = voiceFor(lang, person.gender);
  if (lang === "yue" && (!voice || /zh-CN|zh-TW/i.test(voice.lang))) {
    setStatus(settings.support === "yue" ? "呢部機未有廣東話聲" : "No Cantonese voice is installed. The mouth still moves.");
    playVisemes(visemes, lang);
    return;
  }
  playVisemes(visemes, lang);
  if (!text || !window.speechSynthesis || !voice) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.voice = voice;
  utter.lang = voice.lang;
  utter.onend = () => setFace("idle", "neutral");
  speechSynthesis.speak(utter);
}

function playVisemes(names, lang) {
  const list = names && names.length ? names : ["sil"];
  const step = lang === "en" ? 90 : 125;
  let index = 0;
  setFace("speak", session?.track === "ielts" && session.kind === "mock" ? "examiner" : "question");
  if (portrait) portrait.setViseme(list[0]);
  visemeTimer = setInterval(() => {
    index += 1;
    if (index >= list.length) {
      clearInterval(visemeTimer);
      if (portrait) portrait.setViseme("sil");
      setFace("idle", "neutral");
      return;
    }
    if (portrait) portrait.setViseme(list[index]);
    drawMouth(list[index]);
  }, step);
}

function setFace(next, mood) {
  mode = next;
  if (portrait) portrait.setMode(next, mood);
}

function setStatus(text) {
  const node = document.querySelector("#status");
  if (node) node.textContent = text;
}

let frameHandle = 0;
let last = 0;
function loop(now) {
  frameHandle = requestAnimationFrame(loop);
  if (portrait) portrait.frame(now, Math.min(0.05, (now - last) / 1000 || 0.016));
  last = now;
  if (!portrait) drawMouth(mode === "listen" ? "sil" : undefined);
}

async function mountFace(canvas) {
  if (portrait) {
    cancelAnimationFrame(frameHandle);
    portrait = null;
  }
  const person = partner();
  if (person.mesh) {
    try {
      portrait = new Portrait(canvas);
      await portrait.load(person.portrait, person.mesh_url);
      portrait.setMode("idle", "neutral");
      last = performance.now();
      frameHandle = requestAnimationFrame(loop);
      return;
    } catch (error) {
      portrait = null;
    }
  }
  drawCard(canvas);
  last = performance.now();
  frameHandle = requestAnimationFrame(loop);
}

function drawCard(canvas) {
  const ctx = canvas.getContext("2d");
  const person = partner();
  const palette = {
    amelia: ["#f2d7c4", "#6b3a2a"],
    mei: ["#f3d2c2", "#2c2420"],
    wing: ["#f0cbb8", "#1d1a17"],
    oliver: ["#e7c2a8", "#3a2a22"],
    hao: ["#efd0b8", "#241c16"],
    lok: ["#e8c3aa", "#141210"],
  };
  const [skin, hair] = palette[person.id] || palette.amelia;
  canvas._palette = { skin, hair, ctx };
  drawMouth("sil");
}

function drawMouth(shape) {
  const canvas = document.querySelector("#face");
  if (!canvas || portrait) return;
  const ctx = canvas.getContext("2d");
  const { skin, hair } = canvas._palette || { skin: "#f2d7c4", hair: "#333" };
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#efe6da";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = hair;
  ctx.beginPath();
  ctx.ellipse(w / 2, h * 0.34, w * 0.28, h * 0.22, 0, Math.PI, 0);
  ctx.fill();
  ctx.fillStyle = skin;
  ctx.beginPath();
  ctx.ellipse(w / 2, h * 0.48, w * 0.24, h * 0.28, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#2b241e";
  ctx.beginPath();
  ctx.arc(w * 0.42, h * 0.46, 3, 0, Math.PI * 2);
  ctx.arc(w * 0.58, h * 0.46, 3, 0, Math.PI * 2);
  ctx.fill();
  const open = { aa: 16, E: 8, I: 5, O: 12, U: 8, sil: 2, PP: 1, FF: 4, TH: 6, DD: 6, kk: 7, CH: 6, SS: 3, nn: 4, RR: 6 }[shape || "sil"] || 2;
  ctx.fillStyle = "#6a3030";
  ctx.beginPath();
  ctx.ellipse(w / 2, h * 0.6, 14, Math.max(1, open), 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = hair;
  ctx.font = "12px sans-serif";
  ctx.fillText(partner().name, 8, h - 10);
}

function renderHome() {
  app.innerHTML = `
    <main class="screen">
      <p class="brand">LingoCoach</p>
      <h1>IELTS-style practice</h1>
      <p class="lede">A practice partner, not an official score. Talk on this phone. The key stays on the server.</p>
      <div class="stack">
        <button class="choice" id="drill"><strong>Today’s IELTS drill</strong><span>Part 1, food at home. Amelia asks. You answer.</span></button>
        <button class="choice" id="mock"><strong>Full speaking mock</strong><span>Scripted questions. No coaching until the end.</span></button>
        <button class="choice" id="daily"><strong>Daily talk</strong><span>A cha chaan teng, a London street, or a Beijing hotel.</span></button>
        <button class="ghost" id="settings">Settings</button>
      </div>
      <p class="disclaimer">${boot.key_loaded ? "OpenRouter is on for live lines." : "No OpenRouter key on this machine, so turns use the built-in coach."}</p>
    </main>`;
  document.querySelector("#drill").onclick = () => startIelts("drill");
  document.querySelector("#mock").onclick = () => startIelts("mock");
  document.querySelector("#daily").onclick = () => startDaily();
  document.querySelector("#settings").onclick = openSettings;
}

function startDaily() {
  settings.track = "daily";
  if (!["en", "cmn", "yue"].includes(settings.target)) settings.target = "yue";
  save();
  session = {
    track: "daily",
    scenario: "hk-cha-chaan-teng",
    id: crypto.randomUUID(),
    bubbles: [],
    fired: [],
    goal: "open",
  };
  renderDaily();
  void sendDaily(true);
}

function startIelts(kind) {
  settings.track = "ielts";
  settings.target = "en";
  save();
  session = {
    track: "ielts",
    kind,
    id: crypto.randomUUID(),
    part: 1,
    q: 0,
    bubbles: [],
    pendingReview: null,
    prep: 0,
    speak: 0,
    phase: "question",
  };
  renderIelts();
}

function scenarioRow() {
  return boot.scenarios.find((row) => row.id === session.scenario);
}

function renderDaily() {
  const row = scenarioRow();
  const person = partner();
  app.innerHTML = `
    <main class="screen">
      <div class="top">
        <button class="ghost" id="home">Home</button>
        <div class="grow"><h2>${person.name}</h2><div class="fine">${person.city} · 27</div></div>
        <button class="ghost" id="change">Change</button>
      </div>
      <div class="chips" id="chips"></div>
      <div class="stage">
        <canvas id="face" width="336" height="448" aria-label="${person.name}, 27, ${person.city}"></canvas>
        <div>
          <p class="goal" id="goal">${row.goal[settings.support] || row.goal.en}</p>
          <p class="fine" id="status">Ready</p>
        </div>
      </div>
      <div class="thread" id="thread"></div>
      <div class="composer">
        <button class="icon-btn" id="mic" aria-label="Hold to talk">Mic</button>
        <textarea id="field" placeholder="Type, or hold the mic"></textarea>
        <button class="send" id="send">Send</button>
      </div>
    </main>`;
  const chips = document.querySelector("#chips");
  for (const item of boot.scenarios) {
    const button = document.createElement("button");
    button.className = "chip";
    button.textContent = title(item);
    button.setAttribute("aria-pressed", String(item.id === session.scenario));
    button.onclick = () => {
      if (session.bubbles.some((bubble) => bubble.role === "learner") && !confirm("Start a new practice? This chat stays on this page until you leave.")) return;
      session.scenario = item.id;
      session.bubbles = [];
      session.fired = [];
      settings.target = item.id === "london-directions" ? "en" : item.id === "beijing-hotel-checkin" ? "cmn" : "yue";
      save();
      renderDaily();
      void sendDaily(true);
    };
    chips.append(button);
  }
  document.querySelector("#home").onclick = () => { speechSynthesis?.cancel(); renderHome(); };
  document.querySelector("#change").onclick = openPartners;
  document.querySelector("#send").onclick = () => sendDaily(false);
  wireMic();
  paintThread();
  void mountFace(document.querySelector("#face"));
}

function paintThread() {
  const thread = document.querySelector("#thread");
  if (!thread) return;
  thread.innerHTML = "";
  for (const bubble of session.bubbles) {
    const node = document.createElement("article");
    node.className = `bubble ${bubble.role}`;
    const who = bubble.role === "character" ? (bubble.partnerName || partner().name) : "You";
    node.innerHTML = `<div class="who">${who}</div><div></div>`;
    node.querySelector("div:last-child").textContent = bubble.text;
    if (bubble.phonetic) {
      const phone = document.createElement("div");
      phone.className = "phonetic";
      phone.textContent = bubble.phonetic;
      node.append(phone);
    }
    if (bubble.translation && settings.level !== "advanced") {
      const tr = document.createElement("p");
      tr.className = "fine";
      tr.textContent = bubble.translation;
      node.append(tr);
    }
    if (bubble.coaching) node.append(coachingCard(bubble.coaching));
    if (bubble.review) node.append(reviewCard(bubble.review));
    thread.append(node);
  }
  thread.scrollTop = thread.scrollHeight;
}

function coachingCard(coaching) {
  const card = document.createElement("div");
  card.className = "coach-card";
  if (coaching.praise) {
    const p = document.createElement("p");
    p.textContent = coaching.praise;
    card.append(p);
  }
  for (const hint of coaching.reading_hints || []) {
    const p = document.createElement("p");
    p.textContent = `How it is read: ${hint.term} — ${hint.note}`;
    card.append(p);
  }
  if (coaching.suggested_reply) {
    const p = document.createElement("p");
    p.textContent = `Try saying: ${coaching.suggested_reply}`;
    card.append(p);
    if (coaching.suggested_reply_phonetic) {
      const phone = document.createElement("div");
      phone.className = "phonetic";
      phone.textContent = coaching.suggested_reply_phonetic;
      card.append(phone);
    }
  }
  for (const item of coaching.corrections || []) {
    const p = document.createElement("p");
    p.textContent = `Why: ${item.why}`;
    card.append(p);
  }
  return card;
}

function reviewCard(data) {
  const card = document.createElement("div");
  card.className = "coach-card";
  const note = document.createElement("p");
  note.textContent = "Practice estimate. Pronunciation was not assessed, so there is no overall speaking band.";
  card.append(note);
  for (const row of data.criteria || []) {
    const p = document.createElement("p");
    const band = row.band == null ? "not scored" : `band ${row.band}`;
    p.textContent = `${row.id.replaceAll("_", " ")}: ${band}. ${row.evidence || ""}`;
    card.append(p);
  }
  if (data.practice_answer) {
    const p = document.createElement("p");
    p.textContent = `Practice answer (${data.practice_answer.aim_band}): ${data.practice_answer.text}`;
    card.append(p);
    const why = document.createElement("p");
    why.textContent = data.practice_answer.why;
    card.append(why);
  }
  return card;
}

async function sendDaily(opening) {
  const field = document.querySelector("#field");
  const text = opening ? "" : (field?.value || "").trim();
  if (!opening && !text) return;
  if (!opening) {
    session.bubbles.push({ role: "learner", text });
    field.value = "";
    paintThread();
  }
  const send = document.querySelector("#send");
  if (send) send.disabled = true;
  setStatus("Thinking");
  try {
    const data = await api("/api/turn", {
      session_id: session.id,
      scenario_id: session.scenario,
      partner_id: settings.partner,
      settings,
      history: session.bubbles.filter((bubble) => bubble.role === "learner" || bubble.role === "character").slice(-12).map((bubble) => ({ role: bubble.role, text: bubble.text })),
      fired_signals: session.fired,
    });
    session.fired = data.session?.fired_signals || data.goal.fired;
    session.goal = data.session?.goal_status || data.goal.status;
    const person = partner();
    session.bubbles.push({
      role: "character",
      text: data.character.text,
      phonetic: data.character.phonetic,
      translation: data.character.translation,
      visemes: data.character.visemes,
      partnerName: person.name,
      partnerId: person.id,
    });
    const lastLearner = [...session.bubbles].reverse().find((bubble) => bubble.role === "learner");
    if (lastLearner && data.coaching) lastLearner.coaching = data.coaching;
    paintThread();
    setStatus(data.provider === "fixture" ? "Built-in coach" : data.provider);
    if (settings.autoplay) speak(data.character.text, settings.target, data.character.visemes);
    if (session.goal === "met") setStatus("Goal met");
  } catch (error) {
    setStatus(error.status === 429 ? "Too many turns. Wait a moment." : "The coach is unavailable. You can retry.");
  } finally {
    if (send) send.disabled = false;
  }
}

function renderIelts() {
  const person = partner();
  const question = currentQuestion();
  app.innerHTML = `
    <main class="screen">
      <div class="top">
        <button class="ghost" id="home">Home</button>
        <div class="grow"><h2>${person.name}</h2><div class="fine">IELTS-style ${session.kind} · ${person.city} · 27</div></div>
        <div class="timer" id="clock"></div>
        <button class="ghost" id="change">Change</button>
      </div>
      <div class="stage">
        <canvas id="face" width="336" height="448" aria-label="${person.name}"></canvas>
        <div>
          <p class="goal">Practice estimate only. Not an official score.</p>
          <p class="fine" id="status">${session.kind === "mock" ? "No coaching until the end." : "Drill"}</p>
        </div>
      </div>
      <div class="cue" id="cue"></div>
      <div class="thread" id="thread"></div>
      <div class="composer">
        <button class="icon-btn" id="mic">Mic</button>
        <textarea id="field" placeholder="Type your answer"></textarea>
        <button class="send" id="send">Send</button>
      </div>
    </main>`;
  document.querySelector("#home").onclick = () => { speechSynthesis?.cancel(); clearInterval(session.ticker); renderHome(); };
  document.querySelector("#change").onclick = openPartners;
  document.querySelector("#send").onclick = () => submitIelts();
  wireMic();
  paintCue();
  paintThread();
  void mountFace(document.querySelector("#face"));
  if (settings.autoplay) speak(question, "en", null);
}

function currentQuestion() {
  if (session.part === 1) return boot.ielts.part1.questions[session.q] || boot.ielts.part1.questions[0];
  if (session.part === 2) return boot.ielts.part2.cue.title;
  return boot.ielts.part3.questions[session.q] || boot.ielts.part3.questions[0];
}

function paintCue() {
  const cue = document.querySelector("#cue");
  if (!cue) return;
  if (session.part === 2) {
    const card = boot.ielts.part2;
    cue.innerHTML = `<strong>${card.cue.title}</strong><ul>${card.cue.say.map((line) => `<li>${line}</li>`).join("")}</ul>`;
    if (session.kind !== "mock") {
      const gloss = document.createElement("p");
      gloss.className = "fine";
      gloss.textContent = card.gloss[settings.support] || card.gloss.en;
      cue.append(gloss);
    }
  } else {
    cue.textContent = currentQuestion();
    if (session.kind !== "mock" && session.part === 1) {
      const gloss = document.createElement("p");
      gloss.className = "fine";
      gloss.textContent = boot.ielts.part1.gloss[settings.support] || boot.ielts.part1.gloss.en;
      cue.append(gloss);
    }
  }
}

async function submitIelts() {
  const field = document.querySelector("#field");
  const text = (field.value || "").trim();
  if (!text) return;
  field.value = "";
  session.bubbles.push({ role: "learner", text, part: session.part });
  paintThread();
  const hide = session.kind === "mock";
  if (!hide) {
    setStatus("Reviewing");
    try {
      const data = await api("/api/ielts/review", {
        session_id: session.id,
        kind: "drill",
        part: session.part,
        prompt_id: session.part === 1 ? "food-at-home" : "skill-you-taught",
        target_band: settings.target_band,
        support: settings.support,
        script: settings.script,
        accent: settings.accent,
        speech_ms: session.speechMs || 45000,
        learner_text: text,
      });
      session.bubbles[session.bubbles.length - 1].review = data;
      paintThread();
      setStatus("Practice estimate");
    } catch (error) {
      setStatus("The review is unavailable.");
    }
  }
  advanceIelts();
}

function advanceIelts() {
  if (session.part === 1 && session.q < boot.ielts.part1.questions.length - 1) {
    session.q += 1;
    paintCue();
    if (settings.autoplay) speak(currentQuestion(), "en", null);
    return;
  }
  if (session.part === 1) {
    session.part = 2;
    session.q = 0;
    session.phase = "prep";
    paintCue();
    runPrep();
    return;
  }
  if (session.part === 2) {
    session.part = 3;
    session.q = 0;
    paintCue();
    if (settings.autoplay) speak(currentQuestion(), "en", null);
    return;
  }
  if (session.q < boot.ielts.part3.questions.length - 1) {
    session.q += 1;
    paintCue();
    if (settings.autoplay) speak(currentQuestion(), "en", null);
    return;
  }
  setStatus(session.kind === "mock" ? "Mock finished. Reviews stay off until you ask on the last answer in a later build; this mock kept coaching hidden." : "Drill finished.");
}

function runPrep() {
  let left = 60;
  const clock = document.querySelector("#clock");
  const field = document.querySelector("#field");
  const send = document.querySelector("#send");
  const mic = document.querySelector("#mic");
  if (send) send.disabled = true;
  if (mic) mic.disabled = true;
  session.ticker = setInterval(() => {
    left -= 1;
    if (clock) clock.textContent = `Prep ${left}s`;
    if (left <= 0) {
      clearInterval(session.ticker);
      if (send) send.disabled = false;
      if (mic) mic.disabled = false;
      if (clock) clock.textContent = "Speak 120s";
      setStatus("Part 2. Speak now.");
      let speak = 120;
      session.speechStart = Date.now();
      session.ticker = setInterval(() => {
        speak -= 1;
        if (clock) clock.textContent = `Speak ${speak}s`;
        if (speak <= 0) {
          clearInterval(session.ticker);
          if (field && field.value.trim()) submitIelts();
        }
      }, 1000);
    }
  }, 1000);
}

function wireMic() {
  const mic = document.querySelector("#mic");
  const field = document.querySelector("#field");
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) {
    mic.title = "This browser has no speech recognition. Type instead.";
    return;
  }
  let rec = null;
  let draft = "";
  const start = () => {
    draft = field.value;
    rec = new Rec();
    const lang = settings.target === "yue" ? "zh-HK" : settings.target === "cmn" ? "zh-CN" : settings.accent;
    rec.lang = lang;
    rec.interimResults = true;
    rec.onresult = (event) => {
      let said = "";
      for (let i = 0; i < event.results.length; i++) said += event.results[i][0].transcript;
      field.value = said;
    };
    rec.onend = () => { mic.classList.remove("listening"); setFace("idle", "neutral"); };
    rec.onerror = () => { field.value = draft; mic.classList.remove("listening"); };
    setFace("listen", "listen");
    mic.classList.add("listening");
    setStatus("Listening");
    speechSynthesis?.cancel();
    rec.start();
  };
  const stop = () => { rec?.stop(); mic.classList.remove("listening"); setStatus("Stopped"); };
  mic.addEventListener("pointerdown", (event) => { event.preventDefault(); start(); });
  mic.addEventListener("pointerup", stop);
  mic.addEventListener("pointercancel", stop);
  field.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      document.querySelector("#send")?.click();
    }
  });
}

function openPartners() {
  const sheet = document.createElement("div");
  sheet.className = "sheet";
  const people = boot.partners.map((person) => `
    <button class="person ${person.id === settings.partner ? "on" : ""}" data-id="${person.id}">
      <strong>${person.name}</strong>
      <div class="fine">${person.gender === "woman" ? "Woman" : "Man"} · 27 · ${person.city}</div>
    </button>`).join("");
  sheet.innerHTML = `<article><h2>Change partner</h2><div class="people">${people}</div><button class="ghost" id="close">Close</button></article>`;
  document.body.append(sheet);
  sheet.querySelector("#close").onclick = () => sheet.remove();
  sheet.onclick = (event) => { if (event.target === sheet) sheet.remove(); };
  for (const button of sheet.querySelectorAll(".person")) {
    button.onclick = () => {
      settings.partner = button.dataset.id;
      save();
      sheet.remove();
      const label = document.querySelector(".top h2");
      if (label) label.textContent = partner().name;
      const live = document.createElement("div");
      live.className = "fine";
      live.setAttribute("aria-live", "polite");
      live.textContent = `Now talking with ${partner().name}`;
      document.querySelector(".stage")?.append(live);
      speechSynthesis?.cancel();
      void mountFace(document.querySelector("#face"));
    };
  }
}

function openSettings() {
  const sheet = document.createElement("div");
  sheet.className = "sheet";
  sheet.innerHTML = `
    <article>
      <h2>Settings</h2>
      <label>Support language
        <select id="support">
          <option value="en">English</option>
          <option value="cmn">Putonghua</option>
          <option value="yue">Cantonese</option>
        </select>
      </label>
      <label>Daily target
        <select id="target">
          <option value="en">English</option>
          <option value="cmn">Putonghua</option>
          <option value="yue">Cantonese</option>
        </select>
      </label>
      <label>Level
        <select id="level">
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
        </select>
      </label>
      <label>English accent
        <select id="accent">
          <option value="en-GB">British</option>
          <option value="en-US">American</option>
        </select>
      </label>
      <label>Target band
        <select id="band">${[5, 5.5, 6, 6.5, 7, 7.5, 8].map((n) => `<option value="${n}">${n}</option>`).join("")}</select>
      </label>
      <p class="disclaimer">Transcripts stay in this browser. A turn’s text is sent to the coach. Losing browser data loses history.</p>
      <button class="send" id="done">Done</button>
    </article>`;
  document.body.append(sheet);
  for (const id of ["support", "target", "level", "accent"]) sheet.querySelector("#" + id).value = settings[id];
  sheet.querySelector("#band").value = String(settings.target_band);
  sheet.querySelector("#done").onclick = () => {
    settings.support = sheet.querySelector("#support").value;
    settings.target = sheet.querySelector("#target").value;
    settings.level = sheet.querySelector("#level").value;
    settings.accent = sheet.querySelector("#accent").value;
    settings.target_band = Number(sheet.querySelector("#band").value);
    save();
    sheet.remove();
    renderHome();
  };
}

const catalogue = await fetch("/api/catalogue").then((response) => response.json());
const part1 = catalogue.ielts.find((item) => item.id === "food-at-home");
const part2 = catalogue.ielts.find((item) => item.id === "skill-you-taught");
boot = {
  partners: catalogue.partners,
  scenarios: catalogue.scenarios,
  key_loaded: catalogue.key_loaded,
  ielts: {
    part1,
    part2,
    part3: { questions: part2.part3 || [], gloss: part2.gloss },
  },
};
if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();
renderHome();
