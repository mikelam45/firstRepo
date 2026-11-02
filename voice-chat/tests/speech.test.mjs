import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { expressionPose } from "../app/static/face.js";
import {
  applyLine,
  beginPlayback,
  clampRate,
  COACH_IDS,
  coachDelivery,
  playbackPlan,
  shouldRetrySpeech,
} from "../app/static/speech.js";

const root = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(join(root, "../app/static/app.js"), "utf8");

function voice(name, lang) {
  return { name, lang };
}

const installed = [
  voice("Google UK English Female", "en-GB"),
  voice("Samantha", "en-GB"),
  voice("Victoria", "en-US"),
  voice("Karen", "en-AU"),
  voice("Moira", "en-IE"),
  voice("Ting-Ting", "zh-CN"),
  voice("Sin-Ji", "zh-HK"),
];

function line(coachId, lineLang, voices = installed, baseRate = 1) {
  return coachDelivery(voices, { coachId, lineLang, baseRate });
}

test("idle coach reply speaks and does not cancel", () => {
  const events = [];
  const synth = {
    speaking: false,
    pending: false,
    paused: false,
    cancel() { events.push("cancel"); },
    resume() { events.push("resume"); },
    speak(utterance) { events.push(`speak:${utterance.text}`); this.speaking = true; },
  };
  const plan = playbackPlan(synth, { preserveUnlock: false, userActivated: false });
  assert.equal(plan.cancel, false);
  assert.equal(plan.delayMs, 0);
  assert.equal(plan.volume, 1);
  const utterance = applyLine({ text: "A cup of coffee, please." }, {
    lang: "en-GB",
    rate: Number.NaN,
    pitch: 1.16,
    voice: null,
  });
  const result = beginPlayback(synth, utterance);
  assert.equal(result.spoke, true);
  assert.deepEqual(events, ["speak:A cup of coffee, please."]);
  assert.equal(utterance.volume, 1);
  assert.equal(utterance.rate, 1);
  assert.equal(utterance.pitch, 1.16);
});

test("a playing line is cancelled only when it should be replaced", () => {
  const busy = { speaking: true, pending: false, paused: false };
  assert.equal(playbackPlan(busy, { userActivated: true }).cancel, true);
  assert.equal(playbackPlan(busy, { userActivated: true }).delayMs, 0);
  assert.equal(playbackPlan(busy, { userActivated: false }).delayMs, 80);
  assert.equal(playbackPlan(busy, { preserveUnlock: true, userActivated: false }).cancel, false);
  assert.equal(shouldRetrySpeech("interrupted", 0), true);
  assert.equal(shouldRetrySpeech("canceled", 0), true);
  assert.equal(shouldRetrySpeech("interrupted", 1), false);
  assert.equal(shouldRetrySpeech("not-allowed", 0), false);
});

test("a throwing voice does not stop playback", () => {
  const boom = {
    name: "Boom",
    get lang() { throw new Error("voice lang exploded"); },
  };
  const brokenSetter = {};
  Object.defineProperty(brokenSetter, "voice", {
    set() { throw new Error("cannot assign"); },
  });
  const delivery = coachDelivery(
    [boom, voice("Google UK English Female", "en-GB")],
    { coachId: "chloe", lineLang: "en" },
  );
  assert.equal(delivery.voice.name, "Google UK English Female");
  assert.equal(coachDelivery([boom], { coachId: "amelia", lineLang: "en" }).voice, null);
  assert.doesNotThrow(() => applyLine(brokenSetter, {
    lang: "en-US",
    rate: 0.96,
    pitch: 0.92,
    voice: voice("Victoria", "en-US"),
  }));
  assert.equal(brokenSetter.volume, 1);
  assert.equal(brokenSetter.lang, "en-US");
  assert.equal(beginPlayback(null, { text: "Hi" }).spoke, false);
});

test("four coaches get four different English voices", () => {
  const rows = COACH_IDS.map((id) => line(id, "en"));
  const names = rows.map((row) => row.voice.name);
  assert.deepEqual(names, [
    "Google UK English Female",
    "Victoria",
    "Karen",
    "Samantha",
  ]);
  assert.equal(new Set(names).size, 4);
  assert.equal(rows[0].lang, "en-GB");
  assert.equal(rows[1].lang, "en-US");
  assert.equal(rows[2].lang, "en-AU");
  assert.ok(rows[0].pitch > rows[1].pitch);
  assert.ok(rows[1].pitch < 1);
  assert.equal(new Set(rows.map((row) => row.pitch)).size, 4);
  assert.equal(new Set(rows.map((row) => row.rate)).size, 4);
});

test("Mei uses Mandarin and Celine uses Cantonese when those voices exist", () => {
  const mei = line("mei", "cmn");
  const celine = line("celine", "yue");
  assert.equal(mei.voice.name, "Ting-Ting");
  assert.equal(mei.lang, "zh-CN");
  assert.equal(celine.voice.name, "Sin-Ji");
  assert.equal(celine.lang, "zh-HK");
  const englishMei = line("mei", "en");
  assert.equal(englishMei.voice.name, "Karen");
  assert.notEqual(englishMei.voice, line("chloe", "en").voice);
  assert.notEqual(englishMei.voice, line("amelia", "en").voice);
});

test("missing Cantonese voice still returns a speakable English fallback", () => {
  const englishOnly = installed.filter((item) => !item.lang.startsWith("zh"));
  const celine = line("celine", "yue", englishOnly);
  const chloe = line("chloe", "yue", englishOnly);
  assert.ok(celine.voice);
  assert.notEqual(celine.voice, chloe.voice);
  assert.match(celine.lang, /^en/i);
  assert.notEqual(celine.lang.toLowerCase().startsWith("zh-cn"), true);
  assert.ok(celine.rate > 0 && celine.rate <= 10);
  assert.ok(celine.pitch > 0 && celine.pitch <= 2);
});

test("one installed voice still separates the four coaches by lang, pitch, and rate", () => {
  const only = [voice("Samantha", "en-GB")];
  const rows = ["chloe", "amelia", "mei", "celine"].map((id) => line(id, "en", only, 0.85));
  assert.equal(rows[0].voice.name, "Samantha");
  assert.equal(rows[1].voice, null);
  assert.equal(rows[2].voice, null);
  assert.equal(rows[3].voice, null);
  assert.deepEqual(rows.map((row) => row.lang), ["en-GB", "en-US", "en-AU", "en-GB"]);
  assert.equal(new Set(rows.map((row) => row.pitch)).size, 4);
  assert.equal(new Set(rows.map((row) => `${row.pitch}:${row.rate}`)).size, 4);
  assert.equal(rows[0].rate, clampRate(0.85 * 1.02));
  assert.ok(rows[0].pitch > rows[1].pitch);
  assert.ok(rows[3].pitch < rows[2].pitch);
});

test("speak expression blend does not throw and keeps brows sharp", () => {
  for (const name of ["sil", "aa", "E", "I", "O", "U", "PP", "nope", "", null]) {
    const pose = expressionPose("speak", "happy", name, "aa", 0.4);
    assert.equal(pose.brow, 0);
    assert.equal(pose.smile, 0);
    assert.equal(pose.jaw, 0);
    assert.equal(Number.isFinite(pose.open), true);
  }
  const mixed = expressionPose("speak", "question", "sil", "aa", Number.NaN);
  assert.equal(mixed.brow, 0);
  assert.ok(mixed.open < 0.2);
  const idle = expressionPose("idle", "happy", "aa", "aa", 1);
  assert.ok(idle.smile > 0);
  assert.ok(idle.brow > 0);
  assert.ok(idle.jaw > 0);
  assert.equal(expressionPose("speak", "happy", "aa", "aa", 0).jaw, 0);
});

test("the page unlocks speech on Send and mic and does not drop a missing voice", () => {
  const submit = appSource.slice(appSource.indexOf("async function submitField"), appSource.indexOf("async function postTurn"));
  const mic = appSource.slice(appSource.indexOf("function startMic"), appSource.indexOf("function stopMic"));
  const speak = appSource.slice(appSource.indexOf("function speakText"), appSource.indexOf("async function mountFace"));
  assert.match(submit, /unlockSpeech\(\)/);
  assert.match(submit, /stopSpeaking\(\)/);
  assert.match(mic, /unlockSpeech\(\)/);
  assert.match(speak, /coachDelivery\(/);
  assert.match(speak, /beginPlayback\(/);
  assert.match(speak, /if \(plan\.cancel && synth\)/);
  assert.doesNotMatch(speak, /noCantoneseVoice/);
  assert.doesNotMatch(speak, /voiceFor\(/);
  assert.match(appSource, /function unlockSpeech\(/);
  assert.match(appSource, /pointerdown/);
});
