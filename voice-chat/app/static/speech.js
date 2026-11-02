/** Browser speech playback decisions.
 * Chrome drops the next utterance if cancel() runs while nothing is speaking.
 * Safari ignores speak() that is not inside a user gesture, so a coach reply
 * that starts only after fetch stays silent unless the Send/mic tap already
 * started the engine. Callers speak immediately when they did not just cancel.
 */

export function clampRate(rate) {
  const n = Number(rate);
  if (!Number.isFinite(n) || n <= 0) return 1;
  return Math.min(10, Math.max(0.1, n));
}

export function clampPitch(pitch) {
  const n = Number(pitch);
  if (!Number.isFinite(n)) return 1;
  return Math.min(2, Math.max(0, n));
}

export function engineBusy(synth) {
  return Boolean(synth && (synth.speaking || synth.pending));
}

export function playbackPlan(synth, { preserveUnlock = false, userActivated = false } = {}) {
  const busy = engineBusy(synth);
  const cancel = busy && !preserveUnlock;
  // Same-turn speak keeps a Safari gesture. After a cancel outside a gesture,
  // Chrome needs a short gap or it drops the replacement utterance.
  const delayMs = cancel && !userActivated ? 80 : 0;
  return {
    cancel,
    delayMs,
    resume: Boolean(synth && synth.paused),
    volume: 1,
  };
}

/** Quiet prime spoken synchronously inside Send / mic so later replies are allowed. */
export function unlockUtteranceSpec() {
  return { text: " ", lang: "en-US", volume: 0.01, rate: 1, pitch: 1 };
}

/** speechSynthesis pitch/rate outside this band sounds sped-up or chipmunked. */
export const NATURAL_PITCH = { min: 0.96, max: 1.05 };
export const NATURAL_RATE = { min: 0.96, max: 1.04 };

export function naturalPitch(pitch) {
  const n = clampPitch(pitch);
  return Math.min(NATURAL_PITCH.max, Math.max(NATURAL_PITCH.min, n));
}

export function naturalRate(rate) {
  const n = clampRate(rate);
  return Math.min(NATURAL_RATE.max, Math.max(NATURAL_RATE.min, n));
}

export function applyLine(utterance, { lang, rate, pitch, voice } = {}) {
  utterance.lang = lang || "en-US";
  utterance.volume = 1;
  utterance.rate = naturalRate(rate);
  utterance.pitch = naturalPitch(pitch);
  if (voice) {
    try { utterance.voice = voice; } catch (err) { /* lang is already set; still speak */ }
  }
  return utterance;
}

const STAGE_DIRECTION = /^(?:smiles?|laughs?|sighs?|pauses?|whispers?|softly|quietly|giggles?|chuckles?|nods?|beats?|aside|clears throat|stage direction)$/i;

/** Drop SSML and stage directions. Leave normal sentences alone so the mouth still matches. */
export function naturalizeLine(text) {
  let spoken = String(text ?? "");
  if (!spoken.trim()) return "";
  spoken = spoken.replace(/<\/?[a-zA-Z][^>]*>/g, " ");
  const isStage = (inner) => {
    const body = String(inner || "").trim();
    return STAGE_DIRECTION.test(body) || /\b(laughs?|smiles?|sighs?|whispers?|giggles?|pauses?)\b/i.test(body);
  };
  spoken = spoken.replace(/\*([^*]{1,60})\*/g, (all, inner) => isStage(inner) ? " " : all);
  spoken = spoken.replace(/\[([^\]]{1,60})\]/g, (all, inner) => isStage(inner) ? " " : all);
  spoken = spoken.replace(/\(([^)]{1,48})\)/g, (all, inner) => isStage(inner) ? " " : all);
  // A missing space after .?! gives speechSynthesis a real sentence break.
  // Chinese punctuation already pauses, so those lines stay unchanged.
  spoken = spoken.replace(/([.!?])(?=[A-Za-z])/g, "$1 ");
  spoken = spoken.replace(/[ \t]{2,}/g, " ");
  spoken = spoken.replace(/\s+([,;，、])/g, "$1");
  return spoken.trim();
}

export function shouldRetrySpeech(error, attempt) {
  if (attempt >= 1) return false;
  const reason = String(error || "");
  return reason === "interrupted" || reason === "canceled" || reason === "cancelled";
}

/**
 * Four people, chosen by installed voice first. Pitch and rate stay near 1 so
 * speechSynthesis does not chipmunk or slow them into a robot.
 * - Chloe: warm younger en-GB (Google UK English Female, Serena, enhanced). Pitch 1.03, rate 1.00.
 * - Amelia: another English woman, en-US premium/Google US when Chloe took UK. Pitch 1.00, rate 0.98.
 * - Mei: zh-CN neural (Xiaoxiao / Ting-Ting) for Mandarin; otherwise a third English woman. Pitch 1.01, rate 1.02.
 * - Celine: zh-HK (Sin-Ji) for Cantonese, never Mandarin; otherwise a fourth English voice. Pitch 0.98, rate 0.97.
 * One shared voice still separates them by lang plus these small offsets.
 * A missing list never throws and never means "stay silent".
 */
export const COACH_TIMBRE = {
  chloe: { pitch: 1.03, rate: 1, lang: "en-GB" },
  amelia: { pitch: 1, rate: 0.98, lang: "en-US" },
  mei: { pitch: 1.01, rate: 1.02, lang: "en-AU" },
  celine: { pitch: 0.98, rate: 0.97, lang: "en-GB" },
};

const ROBOT_VOICE = /\b(fred|albert|zarvox|bad news|bahh|bells|boing|bubbles|cellos|deranged|hysterical|junior|pipe|princess|trinoids|whisper|superstar|kathy)\b/i;
const QUALITY_NAME = /neural|premium|enhanced|natural|google|siri|samantha|karen|moira|serena|fiona|victoria|allison|aria|jenny|libby|sonia|kate|xiaoxiao|ting-?ting|sin-?ji|huihui|meijia|shelley/i;

const COACH_IDS = ["chloe", "amelia", "mei", "celine"];
const FEMALE_NAME = /female|woman|samantha|victoria|karen|moira|fiona|serena|kate|libby|sonia|aria|jenny|tessa|zira|hazel|susan|allison|ava|emma|emily|joanna|salli|kimberly|kendra|nicole|natasha|veena|xiaoxiao|huihui|yaoyao|sin-?ji|ting-?ting|meijia|shelley/i;

function normalizeCoach(coachId) {
  const id = String(coachId || "").toLowerCase();
  return COACH_TIMBRE[id] ? id : "amelia";
}

function voiceRecord(voice) {
  if (!voice) return null;
  let tag = "";
  let name = "";
  try { tag = String(voice.lang || ""); } catch (err) { return null; }
  try { name = String(voice.name || ""); } catch (err) { name = ""; }
  const lang = tag.toLowerCase().replace(/_/g, "-");
  if (!lang) return null;
  return { raw: voice, lang, tag: tag || lang, name, female: FEMALE_NAME.test(name) };
}

function safeRecords(voices) {
  const list = Array.isArray(voices) ? voices : [];
  const out = [];
  for (const voice of list) {
    try {
      const rec = voiceRecord(voice);
      if (rec) out.push(rec);
    } catch (err) { /* skip a voice the platform refuses to describe */ }
  }
  return out;
}

function pickBest(records, scoreFn, used) {
  let best = null;
  let bestScore = -Infinity;
  for (const rec of records) {
    if (used.has(rec.raw)) continue;
    let score = 0;
    try { score = scoreFn(rec); } catch (err) { score = 0; }
    if (!Number.isFinite(score)) continue;
    if (score > bestScore || (score === bestScore && best && rec.name.localeCompare(best.name) < 0)) {
      bestScore = score;
      best = rec;
    }
  }
  return best;
}

function qualityScore(rec) {
  if (ROBOT_VOICE.test(rec.name)) return -300;
  let score = 0;
  if (/neural/i.test(rec.name)) score += 60;
  if (/premium/i.test(rec.name)) score += 50;
  if (/enhanced|natural/i.test(rec.name)) score += 45;
  if (/siri/i.test(rec.name)) score += 40;
  if (/google/i.test(rec.name)) score += 36;
  if (QUALITY_NAME.test(rec.name)) score += 12;
  if (/compact/i.test(rec.name)) score -= 80;
  if (rec.female) score += 25;
  return score;
}

function isEnglish(lang) {
  return lang === "en" || lang.startsWith("en-");
}

function isMandarin(lang) {
  return lang.startsWith("zh-cn") || lang.startsWith("cmn") || lang.startsWith("zh-hans");
}

function isCantonese(lang) {
  if (!lang || lang.startsWith("zh-cn") || lang.startsWith("zh-tw") || lang.startsWith("zh-hans")) return false;
  return lang.startsWith("zh-hk") || lang.startsWith("yue");
}

function assignEnglish(records) {
  const english = records.filter((rec) => isEnglish(rec.lang));
  const pool = english.length ? english : records;
  const used = new Set();
  const take = (scoreFn) => {
    const picked = pickBest(pool, scoreFn, used);
    if (picked) used.add(picked.raw);
    return picked;
  };
  const chloe = take((rec) => {
    let score = qualityScore(rec);
    if (rec.lang.startsWith("en-gb")) score += 40;
    if (/google uk english female|uk english female/i.test(rec.name)) score += 55;
    else if (/serena/i.test(rec.name)) score += 36;
    else if (/fiona|kate/i.test(rec.name)) score += 24;
    else if (/samantha/i.test(rec.name)) score += 10;
    return score;
  });
  const amelia = take((rec) => {
    let score = qualityScore(rec);
    if (rec.lang.startsWith("en-us")) score += 45;
    if (/google us english|samantha|victoria|allison|ava/i.test(rec.name)) score += 18;
    if (rec.lang.startsWith("en-gb") && /google uk english female|serena|fiona/i.test(rec.name)) score -= 20;
    return score;
  });
  const mei = take((rec) => {
    let score = qualityScore(rec);
    if (/^en-(au|nz|in|za)/.test(rec.lang)) score += 45;
    if (/karen|moira|fiona/i.test(rec.name)) score += 16;
    return score;
  });
  const celine = take((rec) => {
    let score = qualityScore(rec);
    if (rec.lang.startsWith("en-ie") || /moira/i.test(rec.name)) score += 42;
    else if (rec.lang.startsWith("en-au")) score += 24;
    else if (rec.lang.startsWith("en-gb")) score += 22;
    if (/serena|fiona|samantha|karen/i.test(rec.name)) score += 8;
    return score;
  });
  return { chloe, amelia, mei, celine, pool: "en" };
}

function assignMandarin(records) {
  const zh = records.filter((rec) => isMandarin(rec.lang));
  if (!zh.length) return assignEnglish(records);
  const used = new Set();
  const take = (scoreFn) => {
    const picked = pickBest(zh, scoreFn, used);
    if (picked) used.add(picked.raw);
    return picked;
  };
  const mei = take((rec) => qualityScore(rec) + (/xiaoxiao|huihui|yaoyao|ting-?ting|xiaoyi/i.test(rec.name) ? 36 : 0));
  const chloe = take((rec) => qualityScore(rec));
  const amelia = take((rec) => qualityScore(rec));
  const celine = take((rec) => qualityScore(rec));
  return { chloe, amelia, mei, celine, pool: "cmn" };
}

function assignCantonese(records) {
  const hk = records.filter((rec) => isCantonese(rec.lang));
  if (!hk.length) return assignEnglish(records);
  const used = new Set();
  const take = (scoreFn) => {
    const picked = pickBest(hk, scoreFn, used);
    if (picked) used.add(picked.raw);
    return picked;
  };
  const celine = take((rec) => qualityScore(rec) + (/sin-?ji|meijia/i.test(rec.name) ? 36 : 0));
  const chloe = take((rec) => qualityScore(rec));
  const amelia = take((rec) => qualityScore(rec));
  const mei = take((rec) => qualityScore(rec));
  return { chloe, amelia, mei, celine, pool: "yue" };
}

function assignAll(records, lineLang) {
  if (lineLang === "yue") return assignCantonese(records);
  if (lineLang === "cmn") return assignMandarin(records);
  return assignEnglish(records);
}

function fallbackLang(coachId, lineLang, pool) {
  if (lineLang === "yue") return pool === "yue" ? "zh-HK" : COACH_TIMBRE[coachId].lang;
  if (lineLang === "cmn") return pool === "cmn" ? "zh-CN" : COACH_TIMBRE[coachId].lang;
  return COACH_TIMBRE[coachId].lang;
}

export function coachProsody(coachId, baseRate) {
  const timbre = COACH_TIMBRE[normalizeCoach(coachId)];
  const base = Number.isFinite(Number(baseRate)) && Number(baseRate) > 0 ? Number(baseRate) : 1;
  // Large rate changes are what made the coaches sound synthetic. Beginner
  // 0.85 is lifted into the same natural band as everyone else.
  return { pitch: naturalPitch(timbre.pitch), rate: naturalRate(base * timbre.rate) };
}

/** Voice, lang, pitch, and rate for one coach. Always returns a speakable line. */
export function coachDelivery(voices, { coachId, lineLang = "en", baseRate = 1 } = {}) {
  const id = normalizeCoach(coachId);
  const prosody = coachProsody(id, baseRate);
  try {
    const assigned = assignAll(safeRecords(voices), lineLang || "en");
    const picked = assigned[id];
    if (picked) {
      return {
        coachId: id,
        voice: picked.raw,
        lang: picked.tag || picked.lang || fallbackLang(id, lineLang, assigned.pool),
        pitch: prosody.pitch,
        rate: prosody.rate,
        pool: assigned.pool,
      };
    }
    return {
      coachId: id,
      voice: null,
      lang: fallbackLang(id, lineLang, assigned.pool),
      pitch: prosody.pitch,
      rate: prosody.rate,
      pool: assigned.pool,
    };
  } catch (err) {
    return {
      coachId: id,
      voice: null,
      lang: fallbackLang(id, lineLang, ""),
      pitch: prosody.pitch,
      rate: prosody.rate,
      pool: "",
    };
  }
}

export { COACH_IDS };

/** Speak one line. Does not cancel; the caller cancels only when playbackPlan says so, and only before this call. */
export function beginPlayback(synth, utterance) {
  if (!synth || !utterance) return { spoke: false };
  try { if (synth.paused) synth.resume(); } catch (err) { /* continue */ }
  try {
    synth.speak(utterance);
  } catch (err) {
    return { spoke: false, error: err };
  }
  try { if (synth.paused) synth.resume(); } catch (err) { /* Chrome leaves the engine paused */ }
  return { spoke: true };
}
