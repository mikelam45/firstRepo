import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { expressionPose } from "../app/static/face.js";
import {
  applyLine,
  beginPlayback,
  COACH_IDS,
  COACH_TIMBRE,
  coachDelivery,
  NATURAL_PITCH,
  NATURAL_RATE,
  naturalizeLine,
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
  assert.equal(utterance.pitch, NATURAL_PITCH.max);
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

function assertNatural(row) {
  assert.ok(row.pitch >= NATURAL_PITCH.min && row.pitch <= NATURAL_PITCH.max, row.pitch);
  assert.ok(row.rate >= NATURAL_RATE.min && row.rate <= NATURAL_RATE.max, row.rate);
}

test("four coaches get four different natural English voices", () => {
  const rows = COACH_IDS.map((id) => line(id, "en"));
  const names = rows.map((row) => row.voice.name);
  assert.deepEqual(names, [
    "Google UK English Female",
    "Victoria",
    "Karen",
    "Moira",
  ]);
  assert.equal(new Set(names).size, 4);
  assert.equal(rows[0].lang, "en-GB");
  assert.equal(rows[1].lang, "en-US");
  assert.equal(rows[2].lang, "en-AU");
  assert.equal(rows[3].lang, "en-IE");
  for (const row of rows) assertNatural(row);
  assert.deepEqual(rows.map((row) => row.pitch), COACH_IDS.map((id) => COACH_TIMBRE[id].pitch));
  assert.deepEqual(rows.map((row) => row.rate), COACH_IDS.map((id) => COACH_TIMBRE[id].rate));
  assert.equal(new Set(rows.map((row) => `${row.pitch}:${row.rate}`)).size, 4);
});

test("neural and enhanced voices beat compact and novelty voices", () => {
  const voices = [
    voice("Zarvox", "en-GB"),
    voice("Fred", "en-US"),
    voice("Albert", "en-US"),
    voice("Bad News", "en-US"),
    voice("Pipe Organ", "en-GB"),
    voice("Cellos", "en-GB"),
    voice("Samantha (Compact)", "en-US"),
    voice("Google UK English Female", "en-GB"),
    voice("Microsoft Serena Online (Natural)", "en-GB"),
    voice("Google US English", "en-US"),
    voice("Karen", "en-AU"),
    voice("Moira", "en-IE"),
  ];
  const rows = Object.fromEntries(COACH_IDS.map((id) => [id, line(id, "en", voices)]));
  assert.equal(rows.chloe.voice.name, "Google UK English Female");
  assert.equal(rows.amelia.voice.name, "Google US English");
  assert.equal(rows.mei.voice.name, "Karen");
  assert.equal(rows.celine.voice.name, "Microsoft Serena Online (Natural)");
  for (const id of COACH_IDS) {
    assert.doesNotMatch(rows[id].voice.name, /zarvox|fred|albert|bad news|pipe|cellos|compact/i);
    assertNatural(rows[id]);
  }
  const chloeOnlySerena = line("chloe", "en", [
    voice("Zarvox", "en-GB"),
    voice("Microsoft Serena Online (Natural)", "en-GB"),
    voice("Fred", "en-US"),
  ]);
  assert.equal(chloeOnlySerena.voice.name, "Microsoft Serena Online (Natural)");
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
  assertNatural(celine);
  assert.doesNotMatch(celine.lang, /^zh-cn/i);
});

test("one installed voice still separates the four coaches inside a natural band", () => {
  const only = [voice("Samantha", "en-GB")];
  const rows = ["chloe", "amelia", "mei", "celine"].map((id) => line(id, "en", only, 0.85));
  assert.equal(rows[0].voice.name, "Samantha");
  assert.equal(rows[1].voice, null);
  assert.equal(rows[2].voice, null);
  assert.equal(rows[3].voice, null);
  assert.deepEqual(rows.map((row) => row.lang), ["en-GB", "en-US", "en-AU", "en-GB"]);
  for (const row of rows) assertNatural(row);
  assert.equal(new Set(rows.map((row) => row.pitch)).size, 4);
  assert.equal(new Set(rows.map((row) => `${row.pitch}:${row.rate}:${row.lang}`)).size, 4);
  assert.ok(rows.every((row) => row.rate >= NATURAL_RATE.min));
  assert.ok(rows[0].pitch > rows[3].pitch);
});

test("ordinary lines stay intact and stage directions are not spoken", () => {
  assert.equal(naturalizeLine("A cup of coffee, please."), "A cup of coffee, please.");
  assert.equal(naturalizeLine("你好。我想要一杯咖啡。"), "你好。我想要一杯咖啡。");
  assert.equal(naturalizeLine("(smiles) Hello there."), "Hello there.");
  assert.equal(naturalizeLine("Hello.World"), "Hello. World");
  assert.equal(naturalizeLine("<speak>Hello <break time=\"500ms\"/> there</speak>"), "Hello there");
  assert.equal(naturalizeLine("*laughs* Good morning."), "Good morning.");
  assert.equal(naturalizeLine("Try the small one (oat milk)."), "Try the small one (oat milk).");
  assert.equal(naturalizeLine(""), "");
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
  assert.match(speak, /naturalizeLine\(/);
  assert.match(speak, /beginPlayback\(/);
  assert.match(speak, /if \(plan\.cancel && synth\)/);
  assert.doesNotMatch(speak, /noCantoneseVoice/);
  assert.doesNotMatch(speak, /voiceFor\(/);
  assert.match(appSource, /function unlockSpeech\(/);
  assert.match(appSource, /pointerdown/);
});
