import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const helperFile = join(root, "../app/static/transcript.js");
const appFile = join(root, "../app/static/app.js");
const helperSource = readFileSync(helperFile, "utf8");
const { collectTranscript, recognitionLanguage, transcriptPiece } = await import(
  `data:text/javascript,${encodeURIComponent(helperSource)}`
);

function resultList(rows) {
  const list = { length: rows.length };
  for (let i = 0; i < rows.length; i += 1) {
    const alts = rows[i];
    const result = { length: alts.length, isFinal: i === rows.length - 1 };
    for (let j = 0; j < alts.length; j += 1) result[j] = alts[j];
    list[i] = result;
  }
  return list;
}

test("reads a non-iterable result list by index", () => {
  const results = resultList([
    [{ transcript: "hello" }, { transcript: "yellow" }],
    [{ transcript: " there" }],
  ]);
  assert.equal(typeof results[Symbol.iterator], "undefined");
  assert.throws(() => {
    for (const row of results) {
      if (row) break;
    }
  }, TypeError);
  assert.equal(collectTranscript(results), "hello there");
  assert.equal(transcriptPiece(results, 0), "hello");
  assert.equal(transcriptPiece(results, 1), " there");
});

test("reads item() rows when index properties are missing", () => {
  const rows = [[{ transcript: "早晨" }], [{ transcript: "呀" }]];
  const results = {
    length: rows.length,
    item(index) {
      const alts = rows[index];
      return {
        length: alts.length,
        item(altIndex) {
          return alts[altIndex];
        },
      };
    },
  };
  assert.equal(results[0], undefined);
  assert.equal(collectTranscript(results), "早晨呀");
});

test("ignores empty result lists", () => {
  assert.equal(collectTranscript(null), "");
  assert.equal(collectTranscript(undefined), "");
  assert.equal(collectTranscript({}), "");
  assert.equal(collectTranscript({ length: 1, 0: { length: 1, 0: {} } }), "");
});

test("maps the session language", () => {
  assert.equal(recognitionLanguage("en", "en-GB"), "en-GB");
  assert.equal(recognitionLanguage("en", "en-US"), "en-US");
  assert.equal(recognitionLanguage("en", ""), "en-GB");
  assert.equal(recognitionLanguage("cmn", "en-GB"), "zh-CN");
  assert.equal(recognitionLanguage("yue", "en-GB"), "zh-HK");
});

test("helper avoids for-of and the page keeps the toggle", () => {
  const app = readFileSync(appFile, "utf8");
  assert.match(helperSource, /for \(let i = 0; i < results\.length; i \+= 1\)/);
  assert.doesNotMatch(helperSource, /for\s*\(\s*(?:const|let|var)\s+\w+\s+of\s+/);
  assert.match(app, /function toggleMic\(/);
  assert.match(app, /for \(let i = 0; i < results\.length; i \+= 1\)/);
  assert.match(app, /transcriptPiece\(results, i\)/);
  assert.match(app, /continuous = false/);
  assert.match(app, /window\.SpeechRecognition \|\| window\.webkitSpeechRecognition/);
  assert.match(app, /english-teacher/);
  assert.match(app, /TEACHER_ID/);
  assert.doesNotMatch(app, /for\s*\(\s*(?:const|let|var)\s+\w+\s+of\s+results\)/);
});
