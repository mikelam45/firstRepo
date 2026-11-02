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

export function applyLine(utterance, { lang, rate, pitch, voice } = {}) {
  utterance.lang = lang || "en-US";
  utterance.volume = 1;
  utterance.rate = clampRate(rate);
  utterance.pitch = clampPitch(pitch);
  if (voice) {
    try { utterance.voice = voice; } catch (err) { /* lang is already set; still speak */ }
  }
  return utterance;
}

export function shouldRetrySpeech(error, attempt) {
  if (attempt >= 1) return false;
  const reason = String(error || "");
  return reason === "interrupted" || reason === "canceled" || reason === "cancelled";
}

/**
 * Four coaches, four timbres. Pitch and rate always differ, so a device with
 * only one female voice still separates them. Preferred installed voices:
 * - Chloe: sweet younger en-GB (Google UK English Female, else Samantha). Higher pitch.
 * - Amelia: a different English woman, en-US when Chloe took en-GB. Lower pitch.
 * - Mei: zh-CN when the line is Mandarin; otherwise a third English woman (en-AU / en-IN / en-NZ / en-ZA).
 * - Celine: zh-HK / yue when the line is Cantonese; otherwise a fourth voice (en-AU, else another en-GB).
 * A missing list never throws and never means "stay silent". Cantonese does not fall back to zh-CN.
 */
export const COACH_TIMBRE = {
  chloe: { pitch: 1.16, rate: 1.02, lang: "en-GB" },
  amelia: { pitch: 0.92, rate: 0.96, lang: "en-US" },
  mei: { pitch: 1.04, rate: 1, lang: "en-AU" },
  celine: { pitch: 0.84, rate: 0.9, lang: "en-GB" },
};

const COACH_IDS = ["chloe", "amelia", "mei", "celine"];
const SWEET_GB = /google uk english female|uk english female|samantha|serena|kate|fiona|moira|victoria|karen/i;
const FEMALE_NAME = /female|woman|samantha|victoria|karen|moira|fiona|serena|kate|libby|sonia|aria|jenny|tessa|zira|hazel|susan|allison|ava|emma|emily|joanna|salli|kimberly|kendra|nicole|natasha|veena|xiaoxiao|huihui|yaoyao|sinji|tingting|meijia|shelley|kathy/i;

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
    let score = rec.female ? 80 : 0;
    if (rec.lang.startsWith("en-gb")) score += 40;
    if (SWEET_GB.test(rec.name)) score += 30;
    if (/google uk english female|uk english female/i.test(rec.name)) score += 15;
    else if (/samantha/i.test(rec.name)) score += 8;
    return score;
  });
  const amelia = take((rec) => {
    let score = rec.female ? 80 : 0;
    if (rec.lang.startsWith("en-us")) score += 40;
    if (rec.lang.startsWith("en-gb") && SWEET_GB.test(rec.name)) score -= 10;
    return score;
  });
  const mei = take((rec) => {
    let score = rec.female ? 80 : 0;
    if (/^en-(au|nz|in|za)/.test(rec.lang)) score += 40;
    return score;
  });
  const celine = take((rec) => {
    let score = rec.female ? 80 : 0;
    if (rec.lang.startsWith("en-au")) score += 40;
    else if (rec.lang.startsWith("en-gb")) score += 28;
    else if (rec.lang.startsWith("en-ie")) score += 20;
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
  const mei = take((rec) => (rec.female ? 40 : 0) + (/xiaoxiao|huihui|yaoyao|tingting|xiaoyi/i.test(rec.name) ? 30 : 0));
  const chloe = take((rec) => (rec.female ? 20 : 0) + (SWEET_GB.test(rec.name) ? 5 : 0));
  const amelia = take((rec) => (rec.female ? 20 : 0));
  const celine = take((rec) => (rec.female ? 20 : 0));
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
  const celine = take((rec) => (rec.female ? 40 : 0) + (/sinji|sin-ji|meijia/i.test(rec.name) ? 30 : 0));
  const chloe = take((rec) => (rec.female ? 20 : 0));
  const amelia = take((rec) => (rec.female ? 20 : 0));
  const mei = take((rec) => (rec.female ? 20 : 0));
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
  return { pitch: timbre.pitch, rate: clampRate(base * timbre.rate) };
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
