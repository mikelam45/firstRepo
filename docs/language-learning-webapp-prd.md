# LingoCoach — product and implementation spec

**Product:** mobile-first daily conversation practice in English, Putonghua, and Cantonese.
**This document replaces** the short architecture note and single-file prototype. That note is the product intent. This spec is what an engineer can build against.
**Status:** v1 decisions are closed unless they appear in [Open decisions](#17-open-decisions).

---

## Review of the source note

The source note defines the right product: a roleplay chat, a phonetic line under each coach turn, a “say it more naturally” card, and a phone layout with a microphone. It is not yet a spec. The gaps below are what this document fills.

| Topic | What the source note gives | Why that is not enough to build | Decision in this spec |
| --- | --- | --- | --- |
| Pronunciation feedback | The model “analyzes pronunciation” from the chat prompt, and the UI labels the card “Coach Tip & Pronunciation”. | The model receives text. It never hears the recording, so any comment about how the user pronounced a word is invented. The prototype’s tip even mentions “latte” when the user may not have said it. | v1 gives **reading hints** (how the line is pronounced) and **wording coaching** (grammar, register, completeness). It does not claim to have scored the user’s audio. Phoneme scoring is a later milestone with a separate consent step. |
| Phonetic source | “LLM directly”, plus `ipa-parser`, `pinyin-pro`, and `to-jyutping`. | Models invent IPA, Pinyin, and Jyutping, including wrong tones. `ipa-parser` is not an English grapheme-to-phoneme library. | Libraries annotate every coach line and every suggested reply. The model may name which words to highlight. It does not supply the phonetic string that the UI renders. English IPA comes from `phonemize`. |
| Languages | `TARGET_LANG` and `SUPPORT_LANG` placeholders. | The UI only has a target-language `<select>`. Script, accent, written Cantonese, and “support language equals target language” are unspecified. | Target language, support language, English accent, and Han script are separate settings. Rules for each are in [Language rules](#2-language-rules). |
| Level | A prompt variable: Beginner / Intermediate / Advanced. | No UI, no effect on length, translation, or how many corrections appear. | Level changes turn length, whether the translation starts open, and the correction budget. See [Level behaviour](#41-level-behaviour). |
| Scenario | Four chips that swap a mock greeting. | No role, goal, success condition, vocabulary, or locale. The mock reply is always an English café line. | Each scenario is a content record with a goal the session can complete. Three scenarios are fully specified. |
| Speech | `SpeechRecognition` and `speechSynthesis` with `zh-HK` / `zh-CN` / `en-US`. | The recognition object is not kept, so Stop cannot call `stop()`. `onend` does not clear the recording flag. Cantonese recognition and a `zh-HK` voice are often missing, and speaking Mandarin in their place teaches the wrong language. `user-scalable=no` blocks pinch zoom. | [Speech input and output](#9-speech-input-and-output) is a failure matrix, not a single happy path. |
| Model output | A JSON example inside the system prompt. | Providers wrap JSON in markdown, omit fields, or return prose. The client has no schema, no retry, and no history format. | A versioned JSON schema, a 12-turn history window, one repair retry, and server-side phonetic overwrite. |
| Feedback shape | One string for “grammar / pronunciation” and one better reply. | A learner cannot tell wording advice from a reading hint, and a good utterance still gets a fake correction. | Structured corrections with a type, a max count per level, a praise line, and a rule to skip the rewrite when the utterance is already fine. |
| Persistence and API keys | The HTML file calls nothing. | A browser cannot hold a provider key. Refreshing loses the chat. | `POST /api/turn` holds the key. Transcripts stay in IndexedDB on the device. v1 has no account. |
| “Real-time” | The header promises real-time pronunciation feedback. | The prototype waits 1 second and inserts a canned café reply in every scenario and language. | v1 is turn-based. The learner edits the transcript, then sends. Budget: coach response p95 under 3 seconds, excluding speech recognition. |

---

## 1. Product

### 1.1 Job to be done

An adult learner in Hong Kong opens the app for a few minutes, walks through one everyday scene, and leaves with:

1. a reply they could actually say, in the target language;
2. a phonetic line they can trust (IPA, Pinyin, or Jyutping);
3. at most a couple of concrete wording fixes, explained in the support language;
4. the scene advanced by one step (the clerk asks the next real question, the directions get more specific, the check-in moves forward).

### 1.2 People

v1 is for adult self-learners who already read the support language fluently and are practising a target language for daily life. The implied mix is Hong Kong: Cantonese daily speech, Putonghua for the Mainland, English for work and travel. The product does not diagnose a level, teach children, or prepare an exam paper.

### 1.3 v1 includes

- One chat screen, three target languages, three support languages, three levels.
- Three scenarios, fully specified in [§6](#6-scenario-content). Three more are named and stay off the chip row until they have the same content record.
- Text send, press-to-talk where the browser can recognize the target language, tap-to-hear where the device has a matching voice.
- Coaching card on the learner’s bubble, phonetic line and translation on the character’s bubble.
- Local transcript history on this device.

### 1.4 v1 excludes

- Accounts, sync, classrooms, assignments, streaks, and payments.
- Phoneme scores, waveforms, and “you said /θ/ wrong” judgments.
- Free chat with no scenario. Every session has a scene and a goal.
- Writing essays, character-handwriting practice, and tone-drill games.
- Offline recognition. The page can show old transcripts offline. A new coach turn needs the network.

### 1.5 Done for v1

A learner can finish the cha-chaan-teng scene in Cantonese, on a phone, with Jyutping that matches `to-jyutping`, a support-language explanation, and a goal state of “bill requested”, without the UI claiming it heard their tones.

---

## 2. Language rules

Three settings are independent:

| Setting | Values | What it controls |
| --- | --- | --- |
| Target language | `en`, `cmn`, `yue` | The character’s lines, the learner’s expected lines, the phonetic system, STT/TTS language. |
| Support language | `en`, `cmn`, `yue` | UI chrome, translations, coaching explanations. |
| Han script | `Hant`, `Hans` | Characters in Putonghua and Cantonese lines, and in support-language Chinese. |

English accent is a fourth setting, `en-GB` (default) or `en-US`. It selects the IPA inventory and the preferred TTS voice. Scenario vocabulary still follows the scene’s locale (a London scene says “lift” and “queue”).

When support language equals target language, hide the translation line. Phonetics and coaching stay.

### 2.1 English

- Learner-facing spelling follows the scene: British spelling in London scenes, American spelling only if a later scene is set in the US. Hong Kong scenes accept both and do not “correct” colour/color.
- IPA is broad, in slashes, word-spaced, with primary stress: `/aɪd laɪk ə ˈkɒfi plaɪz/`.
- One accent per line. `phonemize` is called with `en-GB` or `en-US` for the whole English span. The UI labels the line `IPA · RP` or `IPA · GA`.
- Reading hints that v1 is allowed to give from text alone: `th` as `/θ/` or `/ð/`, final consonants, the difference between the selected accent’s vowels. These are hints about the spelling, worded as “this word is read…”, never as “you said…”.

### 2.2 Putonghua

- Default script is `Hans`. A learner who reads Traditional can switch the Han script to `Hant` without changing the spoken language. Pinyin is generated from the simplified form internally if the library is more reliable that way, then the visible line stays in the chosen script.
- Display Pinyin uses tone marks and spaces between syllables: `nǐ hǎo, wǒ yào bànlǐ rùzhù`. A toggle shows numeric tones (`ni3 hao3`) for learners who want them. `ü` stays `ü`, not `v`.
- Neutral tone has no mark. 儿化 is written only where the wording actually uses it (`一点儿`, `哪儿`), and the Pinyin includes it (`yìdiǎnr`, `nǎr`).
- The model is instructed to use Mainland service Mandarin for Beijing scenes: `您好`, `请问`, `麻烦您`. It does not turn every noun into 儿化.

### 2.3 Cantonese

This is the option most likely to be built wrong, so it is specified tightly.

- The spoken line uses **colloquial written Cantonese** in Traditional characters: `唔該`, `我要一杯熱啡`, `喺`, `嘅`, `咗`, `啩`. Standard written Chinese (`我要一杯咖啡`) is a different register. The coach may show it as the “what this means in written Chinese” gloss for beginners. It is not the line the learner is asked to say.
- Romanization is **LSHK Jyutping** with tone digits glued to the syllable and syllables separated by spaces: `m4 goi1 jat1 bui1 jit6 fe1`. Yale, Sidney Lau, and tone-mark Jyutping are out.
- Particles stay in the sentence (`啦`, `㗎`, `喎`, `吖`). Dropping them to look “textbook” is a worse line, not a better one.
- `唔該` is the request word (ordering, asking someone to move). `多謝` thanks someone for a gift, a compliment, or money. Swapping them is a register correction.
- Hong Kong speech mixes English words (`OK`, `set`, `latte`, `order`). The phonetic line is segmented: Han spans go through `to-jyutping`, Latin spans go through `phonemize` in the selected English accent. Example shape: `m4 goi1 jat1 bui1 jit6 latte /ˈlɑːteɪ/`.
- A `zh-HK` Mandarin voice is the wrong audio. If the device has no Cantonese voice, the speaker button explains that and stays silent.

### 2.4 Code-switch and wrong language

- If the learner writes the support language inside a target-language scene, the character stays in the scene and answers in the target language. The coaching card names the mismatch in one sentence and gives a target-language version of what they tried to say.
- A single borrowed English word inside Cantonese or Putonghua is normal. It is not a mismatch.
- The learner can ask a meta question (“how do I say oat milk?”). The model answers in the support language in the coaching fields, then the character continues the scene in the target language on the next beat. Meta answers do not become the character’s spoken line.

---

## 3. Two different “feedback” features

| Feature | Input | v1 | Honest UI label |
| --- | --- | --- | --- |
| Reading guide | The coach’s text, or the suggested reply | Always, from the phonetic libraries | `Jyutping`, `Pinyin`, or `IPA · RP` / `IPA · GA` |
| Wording coach | The learner’s transcript | Always | `Try saying` / the support-language name |
| Reading hint | Spelling of a word in the learner’s transcript | Only for known hard spots (tones on the suggested line, `th`, final consonants) | `How it is read` |
| Pronunciation score | The audio | Not in v1 | Do not show a score, a colour, or “good pronunciation” |

Later, phoneme scoring can be added only after a vendor is verified for that language. English and Mandarin assessment APIs are common. Cantonese phoneme assessment often is not. The button that would send audio off-device needs its own consent line. Until then the app stores no audio.

Speech-to-text confidence is a weak signal (it measures recognizer certainty, not accent quality). v1 does not surface it as a grade.

---

## 4. Session model

### 4.1 Level behaviour

| | Beginner | Intermediate | Advanced |
| --- | --- | --- | --- |
| Character turn length | ≤ 12 English words, or ≤ 20 Chinese characters | Natural service length | Natural, including asides |
| Translation | Open under the character line | Collapsed; tap to open | Hidden until the learner asks for that line |
| Corrections per learner turn | 1 | 2 | 2, and only if something is actually off |
| Suggested reply | Full utterance they can read aloud | Full utterance | Optional; omit when their line already works |
| Particles, 儿化, slang | Avoid, except the few in the scenario vocab list | Normal | Full colloquial range for that locale |
| Scene complexity | One request at a time | The character can offer a choice | The character can handle a change of mind |

### 4.2 States

```text
pick_scenario
  → in_scene (goal: open)
      → composing            text field focused
      → capturing            mic held down, interim transcript in the field
      → waiting_for_coach    send disabled, character bubble shows a pending state
      → in_scene             coach turn appended, goal still open
  → goal_met                 character closes the scene, composer offers "Practice again"
  → failed_turn              error bubble, learner can retry the same send
```

Changing target language, support language, Han script, accent, level, or scenario discards the current thread. If the thread already has a learner turn, confirm first: “Start a new practice? This chat stays in History.”

### 4.3 Opening the scene

Starting a session sends `POST /api/turn` with `history: []`. The server tells the model to produce the opening line only: `coaching` is `null`, `goal.status` is `open`, `goal.fired` is `[]`. The opening consumes one character turn and counts toward the rate limit. It does not count as a learner turn, so the learner-turn cap is unchanged.

### 4.4 One learner turn

1. Learner commits text (typed, or recognized then edited).
2. Client appends the learner bubble immediately, with the coaching card in a loading state.
3. Client `POST /api/turn` with the scenario id, settings, and the last 12 turns of **text only**. Phonetic strings are not sent back to the model.
4. Server calls the model with the schema in [§10](#10-model-contract).
5. Server replaces `character.phonetic` and `coaching.suggested_reply_phonetic` with library output. The model’s phonetic fields are discarded.
6. Server returns the merged JSON. Client renders it and, if a matching voice exists and the learner has not muted auto-play, speaks the character line once.

Auto-play is on by default and remembered. Starting a recording cancels any speech in progress.

### 4.5 Goal

Each scenario has `success_signals`: short descriptions of learner intents. The model sets `goal.status` to `open` or `met` and copies the signal id it believes fired. The client shows a one-line goal (“Order a drink and ask for the bill”) and, when `met`, a closing state. The model does not invent a new goal mid-scene.

A beginner session also ends after 8 learner turns if the goal is still open, with the character offering to wrap up. Intermediate and advanced use 12. This cap is in the prompt and enforced by the server (the server sends `turns_remaining`).

---

## 5. Screen

One column, `100dvh`, safe-area padding, no pinch-zoom lock. The source prototype’s `maximum-scale=1, user-scalable=no` is dropped.

```text
header:  mark, scenario name, settings button
goal:    one line, muted
chips:   scenarios, horizontal scroll, 44px row height
thread:  flex 1, own scroll
composer: mic, field, send — sitting above the home indicator
```

### 5.1 Bubbles

**Character bubble**

- Target-language text, 16px, default locale font stack that covers Traditional Chinese and Latin.
- Speaker button, 44×44, `aria-label` from the support language (“Play line”). Disabled look plus a tooltip when no voice exists.
- Phonetic line in a monospace face. Long lines wrap; they do not scroll horizontally.
- Translation in the support language, or a “Show translation” control when the level collapses it.
- If the library marked a syllable ambiguous, that syllable is dotted. Tap shows the other candidate readings. v1 does not ask the learner to pick.

**Learner bubble**

- The transcript they sent.
- Coaching card, only after the response arrives:
  - praise, one short sentence, when present;
  - `How it is read`, only when `reading_hints` is non-empty;
  - `Try saying`, the suggested line plus its phonetic line and a speaker button;
  - `Why`, one or two sentences in the support language.
- When `corrections` is empty and there is no suggested reply, the card is praise only. It does not say “Better reply” with a paraphrase of the same sentence.

### 5.2 Composer

- Placeholder in the support language: “Type, or hold the mic”.
- Send is disabled when the trimmed field is empty or a request is in flight.
- Mic is press-and-hold (`pointerdown` / `pointerup` / `pointercancel`). Releasing with a non-empty interim transcript leaves the text in the field. It does not auto-send. Learners need to see recognition errors before they are coached on them.
- A keyboard user can toggle capture with Space while the mic button is focused, and Enter sends.
- Interim recognition results replace the field text for the duration of the hold. The previous draft is restored if recognition ends with an empty result or an error.
- `aria-live="polite"` announces “Listening” and “Stopped”.
- Recording state uses colour and the word “Listening”, not colour alone, and not a looping scale animation when `prefers-reduced-motion` is set.

### 5.3 Settings sheet

- Target language, support language, level, Han script, English accent, auto-play, Pinyin tone marks vs numbers.
- Stored in `localStorage` under `lingocoach.settings.v1`.
- Han script is hidden when the target is English and the support language is English.

### 5.4 History

A list of past sessions: scenario, target language, date, goal met or not. Opening one is read-only. “Practice again” starts a new session with the same settings. Cap 50 sessions; the oldest transcript is dropped.

### 5.5 Copy rules

Support language drives chrome. Scenario titles exist in all three support languages in the content file. Coaching prose is the model’s job, in the support language, and the UI does not machine-translate it again.

---

## 6. Scenario content

### 6.1 Schema

```ts
type Lang = "en" | "cmn" | "yue";
type Level = "beginner" | "intermediate" | "advanced";

type Scenario = {
  id: string;
  locale: "HK" | "London" | "Beijing";
  title: Record<Lang, string>;
  icon: string; // emoji, decorative; the title is the accessible name
  role_ai: Record<Lang, string>;
  role_learner: Record<Lang, string>;
  goal: Record<Lang, string>;
  success_signals: { id: string; description: string }[];
  vocab: {
    id: string;
    say: Record<"en" | "cmn" | "yue", string>; // what to say in that target language
    gloss: Record<Lang, string>;
  }[];
  cultural_notes: string[]; // injected into the prompt, English, short
  opening_hint: Record<Level, string>; // guidance for the model, not shown raw
};
```

The practice is explicitly a practice: the character speaks the target language even when a real person in that city would not. Place names, currency, and politeness stay true to `locale`.

### 6.2 `hk-cha-chaan-teng`

| Field | Value |
| --- | --- |
| Locale | HK |
| Titles | Coffee at a cha chaan teng / 茶餐廳點餐 / 茶餐廳叫嘢飲 |
| AI role | Counter staff |
| Learner role | Customer |
| Goal | Order a drink, change or confirm one detail (ice, sugar, temperature), and ask for the bill |
| Signals | `ordered_drink`, `confirmed_detail`, `asked_for_bill` — goal is met when all three have fired |

Cultural notes for the prompt:

- Requests use `唔該`. Thanks for the drink once it is handed over can be `多謝`.
- Drinks are often `熱` / `凍`, `走甜` / `少甜` / `正常甜`, `走冰`. `咖啡` in speech is often `啡`.
- Staff speak quickly and practically. They do not make a speech about the origin of the beans.
- Prices, if mentioned, are in HKD. No tipping ritual.

Vocab the model should prefer at beginner level: `唔該`, `一杯`, `熱啡`, `凍檸茶`, `走甜`, `少冰`, `埋單`, `好多謝` is not required. Beginner suggested replies stay inside this list plus the drink they asked for.

Opening hint, beginner: staff greet and ask what they would like, in one short line. Intermediate: greet and offer the day’s iced special in one extra clause. Advanced: greet, note the queue briefly, ask the order.

### 6.3 `london-directions`

| Field | Value |
| --- | --- |
| Locale | London |
| Titles | Asking the way / 伦敦问路 / 倫敦問路 |
| AI role | A person on the pavement near a Tube entrance |
| Learner role | A visitor |
| Goal | Ask the way to a named station entrance, understand one landmark, and confirm the turn |
| Signals | `named_destination`, `checked_a_landmark`, `confirmed_the_turn` |

Cultural notes:

- British English: lift, queue, way out, Tube, pavement. The polite frame is “Excuse me” and “Could you tell me…”.
- The character gives at most two steps, then a landmark (“you’ll see the roundel”). They do not list five turns.
- They do not ask for money.

Opening hint: the character is mid-stride, says a short “hi, you look a bit lost” only at advanced; at beginner they simply notice the learner and wait to be asked, with a one-line “Excuse me?” prompt from them if the learner is silent… Silence is not a turn. The first bubble is the character offering help in one line: “Hi — where are you trying to get to?”

### 6.4 `beijing-hotel-checkin`

| Field | Value |
| --- | --- |
| Locale | Beijing |
| Titles | Hotel check-in / 酒店入住 / 酒店入住 |
| AI role | Front-desk clerk |
| Learner role | Guest with a reservation |
| Goal | Give a name, confirm dates, and ask one practical question (wifi, breakfast, or late checkout) |
| Signals | `gave_name`, `confirmed_dates`, `asked_extra` |

Cultural notes:

- Mainland service Mandarin, `您好` / `请问` / `麻烦您`.
- The clerk asks for the passport or booking name and the dates. They do not roleplay handing over a real ID number; if the learner starts to dictate a long number, the clerk says a booking name is enough.
- 儿化 only in natural spots (`这儿`, `一点儿`), not on `房间` or `早餐`.

Opening hint, beginner: “您好，请问您有预订吗？”

### 6.5 Remaining three, same schema, not fully scripted here

| id | Locale | Goal, one line |
| --- | --- | --- |
| `hk-taxi` | HK | Give a destination, confirm the route or tunnel, say when to stop |
| `hk-market` | HK | Ask a price, react, and buy or decline |
| `beijing-restaurant` | Beijing | Book or order for two, state one dietary limit, confirm the order |

Content for these three is written in the same shape as §6.2–6.4 before they are enabled in the chip row. A chip with no content record is not shown.

---

## 7. Coaching rules

The model returns structured coaching. The server checks it. The UI renders it.

### 7.1 Correction types

| type | Use |
| --- | --- |
| `register` | Politeness or locale fit: `我要` → `唔該`; “I want a coffee” → “Could I get a coffee, please.” |
| `vocabulary` | A word that does not belong to this scene or this language’s daily usage. |
| `grammar` | A form that blocks understanding. |
| `completeness` | The clerk cannot act yet: no size, no destination, no name. |
| `mismatch` | The utterance is in the wrong language. |

`reading` is not a correction type. Reading hints are a separate array and never claim the microphone heard a tone.

### 7.2 When to stay quiet

- If the utterance already achieves the beat, `corrections` is `[]` and `suggested_reply` is `null`. `praise` names what worked (“You used 唔該 for the request.”).
- Do not rephrase a fine line into a fancier one. Intermediate learners lose trust when every turn grows longer.
- At most one correction of each type, and no more than the level’s budget. Prefer the correction that would most change what the clerk does next.
- Explanations are in the support language, two sentences maximum, no rubric scores, no percentages.

### 7.3 Suggested reply

- Same intent as the learner, plus the one correction.
- In the target language, in the orthography from §2.
- Short enough for the level.
- The phonetic line under it is computed on the server from this text, not copied from the model.

---

## 8. Phonetic pipeline

Runs on the server for every `character.text` and every non-null `suggested_reply`. The client renders `phonetic` and does not recompute it, so a phone with a small CPU still shows the line instantly.

### 8.1 Segment, then convert

```text
text
  → spans of: han | latin | numeral | other
  → han + target cmn  → pinyin-pro, tone marks (or numeric if the setting says so)
  → han + target yue  → to-jyutping getJyutpingText
  → latin             → phonemize toIPA, language en-GB or en-US
  → numeral           → left as digits (prices, platforms, room numbers)
  → other             → dropped from the phonetic line (punctuation, emoji)
  → join spans with a single space
```

Libraries:

| Language | Package | Call |
| --- | --- | --- |
| English IPA | `phonemize` | `toIPA(span, "en-GB" \| "en-US")` |
| Putonghua | `pinyin-pro` | `pinyin(span, { toneType: "symbol" \| "num", type: "string" })`. Use surname mode only on a span the scenario marks as a personal name. |
| Cantonese | `to-jyutping` | `getJyutpingText(span)`. Ambiguous syllables: if `getJyutpingCandidates` returns two leading readings with different tones, set `ambiguous: true` on that syllable. |

`to-jyutping` already returns colloquial readings for written Cantonese (`唔` → `m4`, `啱` → `ngaam1`). Custom overrides use `ToJyutping.customize` only for scenario proper names that the library gets wrong. Overrides live next to the scenario, not in a global patch file of guesses.

### 8.2 Trust boundary

- The UI’s phonetic line is the library line.
- If a Han character has no reading, the server leaves `·` in that position and adds `phonetic_complete: false`. The UI shows the line and does not fill the gap with a model guess.
- The model may return `highlight_terms`: surface strings it wants the learner to notice. The server attaches library readings to those terms for `reading_hints`. Terms that are not substrings of the learner’s text or the suggested reply are dropped.

### 8.3 Golden tests

Check in at least these, and fail CI if a library upgrade changes them without an intentional fixture edit:

| Target | Text | Reading |
| --- | --- | --- |
| yue | 唔該，一杯熱啡，走甜。 | `m4 goi1 jat1 bui1 jit6 fe1 zau2 tim4` |
| yue | 埋單 | `maai4 daan1` |
| cmn | 您好，请问您有预订吗？ | The committed `pinyin-pro` string for this exact input, tone marks, `toneType: "symbol"`. Review the fixture when the library changes; do not hand-edit it to a prettified spacing. |
| cmn | 这儿有一点儿吵 | That fixture contains the 儿化 syllables for `这儿` and `一点儿`. |
| en-GB | Could I get a coffee, please? | `phonemize` `en-GB` output, pinned |
| en-US | Could I get a coffee, please? | `phonemize` `en-US` output, pinned, and it must differ from the GB fixture where the accent differs (`coffee`) |
| yue + en | 唔該一杯 latte | Jyutping span, then an IPA span |

Also pin one heteronym the product cares about, using `customize` if the default reading is the wrong sense for the scenario, and test that the override does not leak into another scenario’s converter instance (`to-jyutping` converters chain without mutating the default).

---

## 9. Speech input and output

Browser speech is a progressive enhancement. The text path is the product.

### 9.1 Recognition

Feature-detect `SpeechRecognition` or `webkitSpeechRecognition`. Keep the instance on the session object so a release calls `stop()`.

| Setting | Value |
| --- | --- |
| `lang` | `en-GB` or `en-US`; `zh-CN`; for Cantonese try `yue-Hant-HK`, and on `language-not-supported` try `zh-HK` once |
| `interimResults` | `true` |
| `continuous` | `false` |
| `maxAlternatives` | `1` |

| Event | Behaviour |
| --- | --- |
| `onresult` interim | Write the hypothesis into the field |
| `onresult` final | Keep it in the field, leave capture |
| `onerror` `not-allowed` | “Microphone is blocked. You can type instead.” |
| `onerror` `network` | “Recognition needs a connection.” |
| `onerror` `no-speech` | Restore the previous draft, clear Listening |
| `onerror` `audio-capture` | “No microphone found.” |
| `onerror` `language-not-supported` and the Cantonese retry also failed | Hide the mic for this target language for the rest of the session. Show “Cantonese recognition isn’t available in this browser. Type in Cantonese.” |
| `onend` | Always clear Listening, even if `onresult` never fired |

Do not pass Cantonese audio to a Mandarin recognizer and then coach the Mandarin transcript as if the learner had written Cantonese. A Mandarin transcript of Cantonese speech is a different sentence.

Chrome’s on-device language list has included Mandarin (`zh-CN`, `zh-TW`) and has omitted Cantonese. Cloud recognizers sometimes accept `yue-Hant-HK`. Availability is a runtime fact. The app discovers it per session. Firefox often has no `SpeechRecognition` at all; iOS browsers share WebKit, so they stand or fall together.

Recognition audio may leave the device for the browser vendor’s service. The settings sheet says so in one sentence. v1 does not run a second recognizer (no Whisper upload) and does not keep the audio.

### 9.2 Synthesis

| Target | Voice language | If no voice |
| --- | --- | --- |
| en | `en-GB` or `en-US` to match the accent setting | Hide auto-play; speaker button explains that no English voice is installed |
| cmn | `zh-CN` | Same, for Putonghua |
| yue | a voice whose `lang` starts with `zh-HK` or `yue` | Same, for Cantonese. Do not fall back to `zh-CN` or `zh-TW` |

Before each `speak`, call `speechSynthesis.cancel()` so lines do not queue. `utterance.rate` is `0.85` at beginner and `1` otherwise. A long-press on the speaker button (or a small rate control in the bubble menu) cycles `0.75 → 1 → 1.15` for that session.

`speechSynthesis.getVoices()` is often empty until `voiceschanged`. The client waits for that event once before deciding a voice is missing.

Server TTS (a neural `zh-HK` voice) is the way Cantonese playback becomes reliable. It is out of v1 unless device checks during implementation show that a majority of target phones have no `zh-HK` voice. If it is pulled into v1, it is a second request, `POST /api/speak`, returning audio for the character line only, with the text already produced by `/api/turn`, and the privacy line updated to say the line is sent to the speech vendor.

---

## 10. Model contract

### 10.1 Request the server sends the provider

System prompt (content, not a specific vendor’s wrapper):

```text
You are LingoCoach, running a spoken-language practice scene.
You play the character described in SCENARIO. You speak only TARGET_LANG
in character.text. You explain only in SUPPORT_LANG, in the coaching fields.

Orthography and politeness are defined in LANGUAGE_RULES (the server
inserts the matching subsection of §2 and the scenario cultural_notes).

Level behaviour is LEVEL_RULES (the server inserts the row of §4.1).

Turns remaining including this reply: TURNS_REMAINING.
If this number is 1, move to a natural closing line. If the learner has
already hit every success signal, set goal.status to "met" and close in
character.

Return a single JSON object matching the schema. No markdown fence.
Do not include phonetic transcriptions; the server adds them.
Do not claim the learner’s pronunciation was good or bad. You cannot hear them.
If their wording already works, return an empty corrections array and
suggested_reply null.
```

The user message is:

```json
{
  "scenario": { "id": "hk-cha-chaan-teng", "locale": "HK", "goal": "...", "signals": [] },
  "settings": { "target": "yue", "support": "en", "level": "beginner", "script": "Hant", "accent": "en-GB" },
  "history": [
    { "role": "character", "text": "唔該，想飲啲咩？" },
    { "role": "learner", "text": "我要咖啡" }
  ]
}
```

History is the last 12 bubbles, oldest first, text only. The new learner line is the last item.

### 10.2 Response schema

`contract` must be `"1"`. Extra keys are ignored. Missing required keys fail validation.

```json
{
  "contract": "1",
  "character": {
    "text": "熱定凍？甜度呢？",
    "translation": "Hot or iced? And how sweet?"
  },
  "coaching": {
    "praise": "You named the drink clearly.",
    "corrections": [
      {
        "type": "register",
        "quote": "我要",
        "why": "In a Hong Kong café, 唔該 is the natural way to make a request. 我要 sounds like a translation from Mandarin."
      }
    ],
    "suggested_reply": "唔該，一杯熱啡。",
    "reading_hints": [
      {
        "term": "啡",
        "note": "Spoken Cantonese often shortens 咖啡 to 啡 in this setting."
      }
    ]
  },
  "goal": { "status": "open", "fired": ["ordered_drink"] },
  "safety": { "refused": false }
}
```

Field rules the server enforces:

| Field | Rule |
| --- | --- |
| `character.text` | Non-empty, target language. Max 280 characters. Required. |
| `character.translation` | Support language. `null` when support equals target. Required key, nullable value. |
| `coaching.praise` | String or `null`. Max 160 characters. |
| `coaching.corrections` | Array, length ≤ level budget. `quote` must be a substring of the latest learner text. `why` in the support language, max 240 characters. |
| `coaching.suggested_reply` | Target language, or `null`. If non-null, it must differ from the learner text after trim and punctuation strip. |
| `coaching.reading_hints` | At most 2. `term` must occur in the learner text or the suggested reply. `note` is support language. |
| `goal.status` | `open` or `met`. |
| `goal.fired` | Subset of the scenario’s signal ids. The server unions these with signals already fired earlier in the session. The model does not need to repeat old ones, but may. |
| `safety.refused` | `true` only for the cases in §13. Then `character.text` is a short in-scene redirect, and `coaching` is `null`. |
| Opening turn | When `history` is empty, `coaching` is `null`. The server skips suggestion phonetics and still attaches `character.phonetic`. |

### 10.3 Parse and repair

1. Take the provider text. If it is inside a ```json fence, unwrap once.
2. `JSON.parse`. On failure, call the provider once more with the same conversation plus: “Your previous reply was not JSON. Return only the object.”
3. Validate. On failure, return HTTP 502 with `{ "error": "coach_unavailable" }` and do not render a half-parsed bubble.
4. Run the phonetic pipeline. Attach `character.phonetic`, `character.phonetic_complete`, and, when a suggestion exists, `coaching.suggested_reply_phonetic`.
5. Drop invalid `reading_hints` and unknown signal ids rather than failing the turn.

Temperature stays low (around 0.4). The scene should be stable across retries of the same prompt in tests. Provider choice is an implementation detail; the contract is the schema. Structured-output mode is used when the provider has it, and the repair path still exists for providers that only return text.

### 10.4 Worked behaviours the prompt must hit

These are acceptance fixtures. The exact wording can vary; the structure cannot.

1. **Cantonese register.** Learner: `我要咖啡`. Suggested reply contains `唔該` and a temperature or a reasonable default question from the character, not from the suggestion. Correction type `register`. Jyutping on the suggestion matches §8.3’s style.
2. **Already good.** Learner: `唔該，一杯熱啡，走甜。` Corrections `[]`, suggestion `null`, praise mentions the request word or `走甜`. Character asks the next real question (size is optional; bill has not been asked).
3. **Wrong language.** Learner: `Can I have a hot coffee?` while target is `yue`. Type `mismatch`. Suggestion is a Cantonese line with the same intent. Character responds in Cantonese to that intent (temperature or confirmation), not with a lecture.
4. **English register, London.** Learner: `I want the station.` Suggestion uses “Could you tell me the way to…” and a station name if they gave none only as a completeness correction, not both a register fix and an invented destination. If they named no station, type `completeness` wins over a polish of “I want”.
5. **Putonghua check-in.** Learner: `我要入住`. Suggestion uses `您好` or `麻烦` and offers a name or dates. Character asks for the booking name.
6. **Do not hear ghosts.** The coaching JSON contains no word meaning the audio was clear, loud, or mispronounced. A unit test scans `praise`, `why`, and `note` for a denylist (`pronunciation was`, `you pronounced`, `your tone`, `口音很`, `你讀錯`).

---

## 11. HTTP API

Base path `/api`. JSON. No cookies required. A generated `client_id` (uuid, localStorage) is sent as `X-Client-Id` for the rate limit.

### `POST /api/turn`

Request:

```json
{
  "session_id": "uuid",
  "scenario_id": "hk-cha-chaan-teng",
  "settings": {
    "target": "yue",
    "support": "en",
    "level": "beginner",
    "script": "Hant",
    "accent": "en-GB",
    "pinyin_tone": "mark"
  },
  "history": [{ "role": "learner", "text": "我要咖啡" }],
  "fired_signals": []
}
```

`history` includes the new learner line. Max 12 items. Each `text` max 500 characters. The server recomputes `turns_remaining` from the count of learner roles and the level cap.

Response `200`: the schema from §10.2 plus phonetic fields and:

```json
{
  "session": {
    "fired_signals": ["ordered_drink"],
    "turns_remaining": 7,
    "goal_status": "open"
  }
}
```

Errors:

| Status | error | Client |
| --- | --- | --- |
| 400 | `invalid_request` | Show the message; do not retry blindly |
| 429 | `slow_down` | “Too many turns. Wait a moment.” Retry-After honoured |
| 502 | `coach_unavailable` | Keep the learner bubble. Offer Retry, which resends the same body |

Rate limit: 30 turns per rolling 10 minutes per `client_id`. The phonetic libraries are local and do not count.

The provider key lives in the server environment. The client bundle has no key. Logs store `session_id`, latency, and validation failures. Logs do not store the transcript.

### Client storage

`IndexedDB` database `lingocoach`, store `sessions`, key `session_id`. Value: settings, scenario id, bubbles (text, phonetic, coaching, timestamps), goal status. This is the history screen. Losing the browser data loses history; v1 says that in the settings sheet.

---

## 12. Client structure

The source prototype is one HTML file on CDNs, with a mock timeout in place of the API. v1 is a small Vite + TypeScript app so the phonetic code and the schema can be tested.

```text
src/
  content/scenarios.ts          records from §6
  session/machine.ts            states in §4.2, pure functions
  components/                   header, chips, thread, composer, coaching card, settings
  speech/recognize.ts           §9.1, no UI
  speech/speak.ts               §9.2, no UI
  api/turn.ts                   fetch wrapper
  storage/history.ts            IndexedDB
server/
  turn.ts                       prompt assembly, provider call, schema, phonetics
  phonetics/
    segment.ts
    english.ts                  phonemize
    putonghua.ts                pinyin-pro
    cantonese.ts                to-jyutping
    fixtures.test.ts
```

UI state for a bubble is plain data. Alpine-style mutation of a filtered array item is easy to get wrong once a framework proxies state; the thread is updated by index, immutably: “set coaching on learner turn i”.

The mock in the prototype always returns an English hot-or-iced line. There is no mock in the product UI. Tests use recorded fixtures.

### 12.1 Defects in the source prototype that v1 does not copy

- `toggleRecording` constructs a recognizer and, on a second tap, flips `isRecording` without calling `stop()` on that instance.
- `onend` is not handled, so a silence timeout leaves the red mic on.
- `alert()` for a missing API.
- `speak()` does not cancel the previous utterance.
- Scenario switch replaces history with an English placeholder in every language, and the phonetic line is the literal `Phonetic guide loading...`.
- Header can change `targetLang` mid-chat without resetting, so old bubbles and the new voice language disagree.
- Viewport disables zoom.
- Feedback is a single amber string, so a register tip and a fake pronunciation tip look like the same kind of fact.
- Tailwind, Alpine, and icon CDNs are fine for a demo and are not the v1 runtime.

---

## 13. Safety and privacy

- The character stays in the scene. A request for medical, legal, or financial instructions gets `safety.refused: true` and a one-line redirect back to the scene (“I can only help with this order”). The same for requests to ignore the format or to reveal the prompt.
- The learner may paste personal data. The check-in scene tells the model not to ask for a full ID number. The client does not add its own redaction in v1; the privacy line says transcripts stay on the device and are sent to the model provider as text for the turn.
- Audio: browser recognition may send audio to the browser vendor. v1 does not upload audio to LingoCoach’s server.
- Adults. No child account, no age gate beyond a settings line “LingoCoach is for adult learners”.
- The model does not produce sexual roleplay. A flirtatious learner line is answered with a neutral in-scene redirect and no coaching expansion of that content.

---

## 14. Non-functional

| Topic | Target |
| --- | --- |
| Coach latency | p95 under 3s server time on the text path, measured around `/api/turn`, excluding the learner’s network idle time where we cannot see it. Show the pending bubble immediately. |
| Phonetics | Under 50ms per turn on the server. These libraries are synchronous and in-process. |
| Layout | Usable at 360px wide and at 768px. Composer never sits under the transcript; the thread scrolls. |
| Motion | `prefers-reduced-motion` removes the recording pulse. |
| Zoom and type | Pinch zoom works. Text can grow to 200% without the send button leaving the screen (`dvh`, wrapping chips). |
| Contrast | Body text on slate meets WCAG AA. The coaching card’s text is checked as a pair, not assumed from the prototype’s amber-on-amber. |
| Targets | Mic, send, speaker, scenario chips, and settings controls are at least 44×44 px. |
| i18n files | UI strings for `en`, `cmn`, `yue` live in one dictionary. Cantonese UI strings are written in colloquial Cantonese, reviewed by a person, not translated from Mandarin by the model and shipped. |

---

## 15. Acceptance tests

**Session**

- Sending an empty or whitespace field does nothing.
- A successful turn renders character text, a library phonetic line, and a coaching card.
- Switching scenario with a non-empty thread asks, then clears, then shows that scenario’s opening from a fixture (tests can stub the first turn).
- Switching target language does the same.
- Level beginner hides nothing of the translation; advanced does not show it until asked.
- Support language equal to target hides the translation control.
- Turn 8 at beginner forces a closing beat in the fixture where `turns_remaining` is 1.
- Goal met when the union of signals covers the scenario list; the composer shows Practice again.

**Coaching**

- Fixtures 1–6 in §10.4.
- A correction whose `quote` is not in the learner text is dropped.
- A suggested reply equal to the learner text is treated as `null`.
- Denylist test on coaching strings.

**Phonetics**

- Golden table in §8.3.
- A missing character reading sets `phonetic_complete: false` and still returns 200.
- English accent toggle changes the IPA fixture and the voice-selection argument.

**Speech**

- No `SpeechRecognition`: mic control is not shown, typing works.
- Cantonese double language-not-supported: mic hidden, explanatory text shown, no request fired.
- `pointerup` calls `stop()` and clears Listening even when no result arrives.
- `speak` cancels the previous utterance; a Cantonese request with only a `zh-CN` voice does not speak.

**API**

- Malformed model output triggers one repair call and then 502, and the learner bubble remains with Retry.
- 31st turn inside the window returns 429.
- The client bundle contains no provider key (build artefact grep).

**History**

- Refresh restores the open session and the settings.
- The 51st saved session drops the oldest.

---

## 16. Build order

Each step is shippable to a developer device and has tests before the next starts.

1. **Scenario records and session functions.** Pure TypeScript: settings, signal union, turn cap, “must confirm before reset”. No UI.
2. **Phonetic pipeline and golden fixtures.** This locks §2 before any model is involved.
3. **`/api/turn` with a recorded fixture provider**, schema validation, repair branch, phonetic overwrite. Contract tests in §10.4 run against the fixture provider in CI, and against a live provider only in a manual or nightly check so CI does not depend on a key.
4. **Chat UI, text only.** Thread, coaching card, settings, history. The pending and error states are part of this step, not a follow-up.
5. **Recognition and synthesis**, behind the failure matrix in §9. Device pass: one recent iPhone (Safari), one Android Chrome, one desktop Chromium, one Firefox (expect text-only recognition).
6. **Copy pass** for the three UI languages, by a person, for the strings introduced above.

Server TTS and phoneme scoring are not steps in this list.

---

## 17. Open decisions

These are deliberately not decided here:

1. **Live provider.** Any provider that can return the schema is acceptable. Pick one when the key and the latency budget are known. The repair path stays either way.
2. **Cantonese TTS in v1.** Decide after the device pass in step 5. If `zh-HK` voices are rare on the phones we care about, add `POST /api/speak` before calling v1 done. The rest of the contract does not change.
3. **Han script default for Cantonese support text** is `Hant`. Putonghua target lines default to `Hans`. Whether a single script toggle should split “script for target lines” from “script for UI” is worth a second look once real Traditional-speaking Mandarin learners use it. v1 uses one toggle for all Han text.
4. **Accounts.** Not in v1. When they exist, history moves off the device and the privacy line is rewritten first.

---

## 18. Source note, kept as intent

The source note’s four product points stay in force, with the meanings this spec gives them:

1. **Roleplay** means a scenario record with a goal and success signals, not a free prompt.
2. **Trilingual** means an independent target language and support language, plus an explicit Cantonese orthography and an English accent.
3. **Dual feedback** means a library phonetic line and a structured wording card. It does not mean an audio grade.
4. **Mobile-first** means the composer, the 44px controls, the failure states for mic and voice, and a layout that still works when the type is enlarged.
