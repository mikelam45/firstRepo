import { Portrait, englishVisemes, pinyinVisemes } from "./face.js";

const LINES = [
  {
    speaker: "amelia",
    mood: "happy",
    segments: [
      { lang: "en-GB", text: "Hello. I'm Amelia, and I'll be your examiner today." },
    ],
  },
  {
    speaker: "mei",
    mood: "encourage",
    segments: [
      {
        lang: "zh-CN",
        text: "我先用普通话说明。她是英国考官，现在开始口语练习。",
        pinyin: "wo xian yong pu tong hua shuo ming ta shi ying guo kao guan xian zai kai shi kou yu lian xi",
      },
    ],
  },
  {
    speaker: "amelia",
    mood: "question",
    segments: [
      { lang: "en-GB", text: "Let's begin. Do you usually cook at home?" },
    ],
  },
  {
    speaker: "mei",
    mood: "happy",
    segments: [
      {
        lang: "zh-CN",
        text: "她问你平时是不是在家做饭。你可以这样回答。",
        pinyin: "ta wen ni ping shi shi bu shi zai jia zuo fan ni ke yi zhe yang hui da",
      },
      { lang: "en-GB", text: "I usually cook at home, because it is healthier." },
    ],
  },
];

const faces = {};
let last = performance.now();
let playing = false;

const subtitle = document.querySelector("#subtitle");
const playButton = document.querySelector("#play");
const statusNodes = {
  amelia: document.querySelector("#amelia-status"),
  mei: document.querySelector("#mei-status"),
};

function tick(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  for (const face of Object.values(faces)) {
    if (face) {
      face.resize();
      face.frame(now, dt);
    }
  }
  requestAnimationFrame(tick);
}

function setStatus(speaker, text) {
  statusNodes[speaker].textContent = text;
}

function applyHashPose() {
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  const pose = params.get("pose");
  const lineIndex = params.get("line");
  if (!pose && lineIndex == null) return false;
  const viseme = pose && pose !== "smile" && pose !== "question" && pose !== "listen" ? pose : "sil";
  for (const [name, face] of Object.entries(faces)) {
    if (pose === "listen") {
      face.setMode("listen");
      face.setViseme("sil");
      face.setLook(name === "amelia" ? 0.8 : -0.8);
    } else if (pose === "smile" || pose === "question") {
      face.setMode("speak", pose === "smile" ? "happy" : "question");
      face.setViseme(pose === "smile" ? "E" : "aa");
      face.setLook(0);
    } else if (pose) {
      face.setMode("speak", "neutral");
      face.setViseme(viseme);
      face.setLook(0);
    }
  }
  if (lineIndex != null) {
    const line = LINES[Number(lineIndex)];
    const t = Number(params.get("t") || "0.45");
    holdLine(line, t);
  }
  return true;
}

function holdLine(line, t) {
  const other = line.speaker === "amelia" ? "mei" : "amelia";
  const visemes = line.segments.flatMap(segmentVisemes);
  const index = Math.min(visemes.length - 1, Math.floor(t * visemes.length));
  faces[line.speaker].setMode("speak", line.mood);
  faces[line.speaker].setViseme(visemes[index]);
  faces[line.speaker].setLook(line.speaker === "amelia" ? 0.65 : -0.65);
  faces[other].setMode("listen");
  faces[other].setViseme("sil");
  faces[other].setLook(other === "amelia" ? 0.8 : -0.8);
  subtitle.textContent = line.segments.map((seg) => seg.text).join(" ");
  setStatus(line.speaker, "Speaking");
  setStatus(other, "Listening");
}

function segmentVisemes(segment) {
  return segment.pinyin ? pinyinVisemes(segment.pinyin) : englishVisemes(segment.text);
}

function pickVoice(lang) {
  const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
  const prefix = lang.toLowerCase();
  const ranked = voices.filter((voice) => voice.lang.toLowerCase().replace("_", "-").startsWith(prefix));
  const female = ranked.find((voice) => /female|woman|libby|sonia|aria|fiona|xiaoxiao|huihui|yaoyao|sinji|tingting|meijia/i.test(voice.name));
  return female || ranked[0] || null;
}

function speakSegment(actorName, segment) {
  const visemes = segmentVisemes(segment);
  const face = faces[actorName];
  face.setViseme(visemes[0] || "sil");
  let cursor = 0;
  const stepMs = segment.lang.startsWith("zh") ? 125 : 90;
  const timer = window.setInterval(() => {
    cursor += 1;
    if (cursor >= visemes.length) {
      window.clearInterval(timer);
      return;
    }
    face.setViseme(visemes[cursor]);
  }, stepMs);
  const nominal = visemes.length * stepMs + 280;
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      window.clearInterval(timer);
      face.setViseme("sil");
      resolve();
    };
    const fallback = window.setTimeout(finish, nominal);
    if (!window.speechSynthesis) return;
    const utterance = new SpeechSynthesisUtterance(segment.text);
    utterance.lang = segment.lang;
    utterance.rate = segment.lang.startsWith("zh") ? 0.95 : 0.94;
    const voice = pickVoice(segment.lang);
    if (voice) utterance.voice = voice;
    utterance.onend = () => {
      window.clearTimeout(fallback);
      finish();
    };
    utterance.onerror = () => {
      window.clearTimeout(fallback);
      finish();
    };
    window.speechSynthesis.speak(utterance);
  });
}

async function playFrom(start) {
  if (playing) return;
  playing = true;
  playButton.disabled = true;
  window.speechSynthesis?.cancel();
  for (let i = start; i < LINES.length; i++) {
    const line = LINES[i];
    const other = line.speaker === "amelia" ? "mei" : "amelia";
    faces[line.speaker].setMode("speak", line.mood);
    faces[line.speaker].setLook(line.speaker === "amelia" ? 0.7 : -0.7);
    faces[other].setMode("listen");
    faces[other].setViseme("sil");
    faces[other].setLook(other === "amelia" ? 0.85 : -0.85);
    setStatus(line.speaker, "Speaking");
    setStatus(other, "Listening");
    for (const segment of line.segments) {
      subtitle.textContent = segment.text;
      await speakSegment(line.speaker, segment);
    }
    faces[line.speaker].setMode("idle", "neutral");
    faces[line.speaker].setViseme("sil");
    setStatus(line.speaker, "Here");
  }
  faces.amelia.setMode("idle", "neutral");
  faces.mei.setMode("idle", "neutral");
  faces.amelia.setLook(0.35);
  faces.mei.setLook(-0.35);
  setStatus("amelia", "Here");
  setStatus("mei", "Here");
  subtitle.textContent = "Press play to hear the conversation again.";
  playing = false;
  playButton.disabled = false;
}

async function main() {
  faces.amelia = new Portrait(document.querySelector("#amelia-canvas"));
  faces.mei = new Portrait(document.querySelector("#mei-canvas"));
  await Promise.all([
    faces.amelia.load("./amelia.jpg", "./amelia.json"),
    faces.mei.load("./mei.jpg", "./mei.json"),
  ]);
  faces.amelia.setLook(0.35);
  faces.mei.setLook(-0.35);
  faces.amelia.setMode("idle", "neutral");
  faces.mei.setMode("idle", "happy");
  if (applyHashPose()) {
    faces.amelia.nextBlink = 1e15;
    faces.mei.nextBlink = 1e15;
    document.title = "ready";
  } else {
    subtitle.textContent = "Amelia examines in English. Mei explains in Putonghua, and her mouth follows the line.";
    document.title = "ready";
  }
  requestAnimationFrame(tick);
  playButton.addEventListener("click", () => playFrom(0));
  document.querySelectorAll("[data-line]").forEach((button) => {
    button.addEventListener("click", () => playFrom(Number(button.dataset.line)));
  });
  window.speechSynthesis?.addEventListener("voiceschanged", () => {});
}

main().catch((error) => {
  subtitle.textContent = error.message;
});
