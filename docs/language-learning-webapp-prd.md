# LingoCoach — product and implementation spec

**Product:** mobile-first IELTS training, with explanations in English, Putonghua, or Cantonese, plus a separate daily-conversation track in those three languages.
**This document replaces** the short architecture note and single-file prototype. That note is the product intent. This spec is what an engineer can build against.
**Status:** v1 decisions are closed unless they appear in [Open decisions](#17-open-decisions). For `track: "ielts"`, [§19](#19-ielts-focus-training) wins where it differs from the daily-conversation rules.

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

Two tracks share a phone UI, a support language, and the phonetic pipeline.

| Track | Who it is for | What “good” means |
| --- | --- | --- |
| `ielts` | An adult aiming at an IELTS band, usually with Cantonese or Putonghua as the support language. Default home. | A timed speaking practice that behaves like the test, then a review that trains the next band up. |
| `daily` | The same learner, on days they want a life scene rather than the exam. | A finished scene and a line they could actually say. |

IELTS is a trademark of its owners. The product is practice. It is not a test center, not affiliated with IELTS, and it does not show an official score. The public name in the UI is “IELTS-style practice”.

### 1.1 Job to be done

**IELTS track.** A learner sets a target band, does the drill the plan chose (or a full speaking mock), and leaves with:

1. examiner questions in English, spoken where the device has a voice;
2. their own answer, timed;
3. a practice review in the support language: what they covered, one upgrade toward the target band, and a model answer that keeps their facts;
4. pronunciation left blank unless audio was actually assessed;
5. the next drill already chosen from the weakest criterion.

**Daily track.** A learner walks through one everyday scene and leaves with a reply they could say, a library phonetic line, at most a couple of wording fixes in the support language, and the scene one step further on.

### 1.2 People

Adult self-learners who already read the support language. The implied learner is in Hong Kong: they need English for IELTS, and they understand an explanation faster in Cantonese or Putonghua than in examiner English. Speaking is the same test for Academic and General Training; the module setting exists so Writing later uses the right Task 1. The product does not teach children and does not guess a university’s cutoff.

### 1.3 v1 includes

- Home that opens today’s IELTS speaking drill once a target band is set.
- IELTS speaking: Part 1, Part 2, and Part 3 drills, one diagnostic, one scripted full mock, and a review that withholds coaching until the mock ends. Details in [§19](#19-ielts-focus-training).
- Support-language glosses of examiner questions in drills. Glosses are hidden during a mock.
- Daily track: one chat screen, three target languages, three support languages, three levels, and the three scenarios in [§6](#6-scenario-content). Three further daily scenarios stay off the chip row until they have the same content record.
- Text send, press-to-talk where the browser can recognize the language, tap-to-hear where a matching voice exists.
- Local transcript history on this device.

### 1.4 v1 excludes

- Accounts, sync, classrooms, streaks, and payments.
- An official IELTS band, a predicted “this Saturday’s questions”, or past papers and cue cards taken from real tests.
- A speaking band for pronunciation, and any overall speaking band while pronunciation is unscored.
- Listening and Reading implementations. Their content rules are in §19 so a later build does not start from scraped papers.
- Phoneme scores, waveforms, and “you said /θ/ wrong”.
- Free chat with no scenario and no IELTS prompt. Every session has a task.
- Character-handwriting practice and tone-drill games.
- Offline recognition. Old transcripts can be read offline. A new review needs the network.

Writing is specified in §19 and is the build step after speaking. It is not part of the speaking done-line.

### 1.5 Done for v1

Both of these work on a phone:

- **IELTS.** With Cantonese (or Putonghua, or English) as the support language and a target of 6.5, a learner can finish a Part 2 drill: 60 seconds to prepare, a hard stop at 2 minutes, a review that names missed cue bullets, grammar and vocabulary notes in the support language, pronunciation marked “not assessed”, and a 6.5 practice answer that keeps their example. They can also finish a scripted speaking mock with no coaching until the end, and still see no overall band.
- **Daily.** A learner can finish the cha-chaan-teng scene in Cantonese, with Jyutping that matches `to-jyutping`, a support-language explanation, and a goal state of “bill requested”, without the UI claiming it heard their tones.

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
- IELTS does not require a British or American accent. On the IELTS track the accent setting still chooses the IPA and the voice for model answers, and a review must not treat the other accent as an error. Spelling may be British or American inside one answer; mixing them in a single Writing task is the thing the writing review may mention.

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
| IELTS practice band | Transcript, timers, and the prompt | Speaking criteria except pronunciation. See [§19](#19-ielts-focus-training). | `Practice estimate`, with the disclaimer. Never `Your IELTS score`. |

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

Changing target language, support language, Han script, accent, level, scenario, IELTS part, or mock-versus-drill discards the current thread. If the thread already has a learner turn, confirm first: “Start a new practice? This chat stays in History.”

IELTS timers and the rule that a mock shows no coaching until the end are in [§19.4](#194-speaking-session-rules). The daily state diagram does not run a mock.

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
home:    Today's IELTS drill, Full speaking mock, Daily talk
header:  mark, task name, timer (IELTS only), settings
goal:    one line, muted
body:    cue card or question, then the thread
composer: mic, field, send — sitting above the home indicator
```

Daily talk keeps the horizontal scenario chips under the header. IELTS does not use those chips; the prompt comes from the plan in §19.

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

- Track (`ielts` or `daily`), target language, support language, level (daily), Han script, English accent, auto-play, Pinyin tone marks vs numbers.
- IELTS module (`academic` or `general`), target band (5.0–8.0 in half steps, default 6.5), optional exam date.
- Stored in `localStorage` under `lingocoach.settings.v2`. A v1 blob migrates by setting `track` to `ielts` and `target_band` to 6.5.
- Han script is hidden when the target is English and the support language is English. On the IELTS track the target is always English, so the script control only affects support-language Chinese.

### 5.4 History

A list of past sessions: track, task name, date, and either goal-met (daily) or which speaking criteria were assessed (IELTS). Opening one is read-only. “Practice again” starts a new session with the same settings. Cap 50 sessions; the oldest transcript is dropped. IELTS history does not chart bands in tenths. Criterion bands are whole numbers.

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

Rate limit: 30 daily-track turns per rolling 10 minutes per `client_id`. IELTS reviews are a separate budget: 40 review calls per rolling 30 minutes, which covers a diagnostic, a mock’s three part-reviews, and retries. Examiner questions are local content and do not call the model. The phonetic libraries are local and do not count.

The provider key lives in the server environment. The client bundle has no key. Logs store `session_id`, latency, and validation failures. Logs do not store the transcript.

### Client storage

`IndexedDB` database `lingocoach`, store `sessions`, key `session_id`. Value: settings, scenario id or IELTS prompt ids, bubbles (text, phonetic, coaching or IELTS review, timestamps, `speech_ms`), goal status. This is the history screen. Losing the browser data loses history; v1 says that in the settings sheet.

IELTS reviews use `POST /api/ielts/review`, specified in [§19.6](#196-review-contract). `POST /api/turn` stays the daily-track call. A mock does not call `/api/turn` to invent the next examiner question.

---

## 12. Client structure

The source prototype is one HTML file on CDNs, with a mock timeout in place of the API. v1 is a small Vite + TypeScript app so the phonetic code and the schema can be tested.

```text
src/
  content/scenarios.ts          daily records from §6
  content/ielts/speaking.ts     scripted parts from §19
  content/ielts/writing.ts      task prompts from §19.7
  session/machine.ts            daily states in §4.2, pure functions
  session/ieltsTimers.ts        prep and hard stops, pure functions
  session/ieltsPlan.ts          next-drill rule, pure functions
  components/                   header, chips, thread, composer, coaching card, cue card, review, settings
  speech/recognize.ts           §9.1, no UI
  speech/speak.ts               §9.2, no UI
  api/turn.ts                   daily fetch wrapper
  api/ieltsReview.ts
  storage/history.ts            IndexedDB
server/
  turn.ts                       daily prompt assembly, provider call, schema, phonetics
  ielts/review.ts               §19.6
  ielts/lengthRules.ts          word-count gates, no model
  ielts/round.ts                overall rounding, used only when all four criteria exist
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
- IELTS practice refuses requests for questions from a real test date or test center, “what came up in Hong Kong this week”, memorized examiner scripts, or a guarantee of a band. The reply points back to the original prompt bank. The app never asks for a passport or an ID number. The name it uses is a display name the learner types.

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

**IELTS**

- The fixtures in §19.10. Part 2’s client timer stops capture at 120 seconds. A send before 60 seconds of speech returns one continue prompt and only one.
- A review with `pronunciation.status` of `unscored` renders no overall band.
- A covered-bullet quote that is not a substring is stored as not covered.
- The mock thread does not render a coaching card.
- “What questions came up in Hong Kong yesterday?” is refused and does not reveal or invent a test-day list.

---

## 16. Build order

Each step is shippable to a developer device and has tests before the next starts.

1. **Scenario records and session functions.** Pure TypeScript: settings, signal union, turn cap, “must confirm before reset”. No UI.
2. **Phonetic pipeline and golden fixtures.** This locks §2 before any model is involved.
3. **`/api/turn` with a recorded fixture provider**, schema validation, repair branch, phonetic overwrite. Contract tests in §10.4 run against the fixture provider in CI, and against a live provider only in a manual or nightly check so CI does not depend on a key.
4. **Chat UI, text only.** Thread, coaching card, settings, history. The pending and error states are part of this step, not a follow-up.
5. **Recognition and synthesis**, behind the failure matrix in §9. Device pass: one recent iPhone (Safari), one Android Chrome, one desktop Chromium, one Firefox (expect text-only recognition).
6. **Copy pass** for the three UI languages, by a person, for the strings introduced above, including the IELTS disclaimer.
7. **IELTS speaking drills.** Scripted prompts, Part 2 timers, review endpoint, diagnostic, and next-drill rule from §19. Daily chat already works before this starts.
8. **IELTS speaking mock.** Same prompts and the same review, with coaching suppressed until the mock ends and with the client timers hard-stopping each part.
9. **IELTS writing.** Task 1 and Task 2 from §19.7, after the speaking done-line is met.

Server TTS, phoneme scoring, Listening, and Reading are not steps in this list.

---

## 17. Open decisions

These are deliberately not decided here:

1. **Live provider.** Any provider that can return the schema is acceptable. Pick one when the key and the latency budget are known. The repair path stays either way.
2. **Cantonese TTS in v1.** Decide after the device pass in step 5. If `zh-HK` voices are rare on the phones we care about, add `POST /api/speak` before calling v1 done. The rest of the contract does not change.
3. **Han script default for Cantonese support text** is `Hant`. Putonghua target lines default to `Hans`. Whether a single script toggle should split “script for target lines” from “script for UI” is worth a second look once real Traditional-speaking Mandarin learners use it. v1 uses one toggle for all Han text.
4. **Accounts.** Not in v1. When they exist, history moves off the device and the privacy line is rewritten first.
5. **Keeping the microphone audio on device** so a learner can replay a Part 2 take, and so a future pronunciation criterion has something to score. v1 stores timers and transcripts only. Dual-running `MediaRecorder` and `SpeechRecognition` is unreliable on phones, so replay is not a v1 promise.
6. **An in-house raw-score scale** for Listening and Reading. Until that scale is written down and labeled as ours, those skills show “correct out of 40” and no band.

---

## 18. Source note, kept as intent

The source note’s four product points stay in force, with the meanings this spec gives them:

1. **Roleplay** means a scenario record with a goal and success signals, not a free prompt.
2. **Trilingual** means an independent target language and support language, plus an explicit Cantonese orthography and an English accent.
3. **Dual feedback** means a library phonetic line and a structured wording card. It does not mean an audio grade.
4. **Mobile-first** means the composer, the 44px controls, the failure states for mic and voice, and a layout that still works when the type is enlarged.
5. **IELTS-style training** means scripted speaking parts, exam timers, a practice review in the support language, and a next drill. It does not mean an official score. The rules are [§19](#19-ielts-focus-training).

---

## 19. IELTS focus training

IELTS speaking is a face-to-face interview of about 11–14 minutes: Part 1 (familiar questions, about 4–5 minutes), Part 2 (one minute to prepare, then a long turn of one to two minutes, plus a short rounding-off question), and Part 3 (a harder discussion of the same theme, about 4–5 minutes). Academic and General Training candidates take the same Speaking test. Writing differs by module. Listening and Reading differ by module and are not built in v1.

The training idea is: **rehearse under test rules, then teach one step toward the target band, in the support language.** A mock that coaches in the middle is not a mock. A drill that only produces a “more native” paragraph, with no timer and no next task, is not training.

### 19.1 What the learner can trust

| Shown on screen | Source | Label |
| --- | --- | --- |
| Examiner question | Authored prompt bank | The question itself |
| Cue-card bullet missed or covered | Model judgment, accepted only with a verbatim quote from the learner | `Covered` / `Not yet` |
| Too short, too long, under 250 words | Word count and `speech_ms` on the server | A fact, not a band |
| Fluency and coherence, lexical resource, grammatical range | Model band, clamped, plus a quote or a count | `Practice estimate` |
| Pronunciation | Nothing in v1 | `Not assessed` |
| Overall speaking band | Arithmetic on four assessed criteria | Hidden for the whole of v1 speaking, because pronunciation is missing |
| Writing overall | Four text criteria, all assessable from the script | `Practice estimate`, disclaimer still required |
| Listening or Reading band | Not shown. A later build may show correct/40. | No band until §17 item 6 exists |

Every review screen shows this disclaimer, in the support language (English source; Cantonese and Putonghua go through the human copy pass):

> Practice estimate only. This is not an IELTS result, and this app is not an IELTS test center.

When pronunciation is unscored, a second sentence is required: “Pronunciation was not assessed, so there is no speaking band.”

The official test averages four whole-number criteria and rounds the mean with the published convention: a mean ending in .25 rounds up to the next half band, and a mean ending in .75 rounds up to the next whole band. Four whole numbers only produce .00, .25, .50, and .75, so the function is:

```ts
export function roundIeltsMean(bands: [number, number, number, number]): number {
  const mean = (bands[0] + bands[1] + bands[2] + bands[3]) / 4;
  const whole = Math.floor(mean);
  const frac = mean - whole;
  if (frac < 0.25) return whole;
  if (frac < 0.75) return whole + 0.5;
  return whole + 1;
}
```

`roundIeltsMean([6, 6, 6, 7])` is 6.5. `roundIeltsMean([6, 7, 7, 7])` is 7. v1 speaking never calls it. The function ships now so Writing can use it and so nobody “averages the three scores we happen to have” and labels that an IELTS speaking band.

Criterion bands the model returns must be integers from 4 to 8 inclusive. A 9, a 3, a 6.5, or a non-number becomes `unscored` for that criterion. The app does not invent a replacement. Half bands are only for an overall mean, and only when all four criteria were assessed.

### 19.2 Band target and the size of the rewrite

The learner picks `target_band` from 5.0 to 8.0 in half-band steps. Default 6.5. That number is a goal, not a measurement of their current level and not a claim about any university.

The practice answer is aimed at `min(target_band, lowest_assessed_band + 1)`. If every criterion is `unscored`, the aim is `min(target_band, 6)`.

| Lowest assessed band | Target | Aim |
| --- | --- | --- |
| 5 | 6.5 | 6.0 |
| 6 | 7.0 | 7.0 |
| 6 | 6.5 | 6.5 |
| 7 or above | 7.0 | 7.0, and the review says this criterion already meets the target |
| none | 8.0 | 6.0 |

The `+ 1` is what stops a band-5 answer being replaced by a band-8 performance full of idioms the learner will not say. When the aim already equals the target, the review says so instead of inventing a harder rewrite.

The practice answer keeps the learner’s facts. If they taught their sister to make tomato soup, the practice answer is still the sister and the soup. It does not substitute a prettier story.

Length of that practice answer:

| Part | Aim around 6.0 | Aim around 6.5–7.0 | Aim around 7.5–8.0 |
| --- | --- | --- | --- |
| 1 | Two sentences: a direct answer and one reason | Three or four sentences: reason and a short example | A small contrast as well, still not a speech |
| 2 | All four bullets, simple narrative | The same story, with time order and a reason | The same facts, a short reflective close, still a two-minute turn |
| 3 | A position and one reason | Position, reason, and an example | Those, plus a concession or a consequence |

### 19.3 Prompt bank

Examiner questions are **authored strings**. The model does not invent the next question, does not “predict this week’s topics”, and does not paraphrase the cue card during a mock. Stability matters more than variety from a model.

v1 speaking content before the home screen can offer a task:

| Kind | Count | Notes |
| --- | --- | --- |
| Part 1 frames | 8 | Four short questions each |
| Part 2 cue cards | 12 | Four bullets each, plus two rounding-off questions, plus four linked Part 3 questions |
| Diagnostic set | 1 | Fixed, so two diagnostics can be compared: frame `food-at-home`, card `skill-you-taught`, and the first two Part 3 questions of that card |

One frame and one card are written below. The other items use the same schema and stay disabled until the strings exist. Questions are original. Real test questions, Cambridge papers, and “cue cards from Saturday in Wan Chai” are not imported.

```ts
type SpeakingFrame = {
  id: string;
  part: 1 | 2 | 3;
  topic_tag: string;
  linked_cue_id?: string;
  questions?: string[];          // part 1 and part 3
  cue?: { title: string; say: string[] };
  rounding_off?: string[];       // part 2, ask the first only
  gloss: Record<"en" | "cmn" | "yue", string>;
};
```

**`food-at-home` (Part 1), topic `food`**

1. Do you usually cook, or does someone else cook in your home?
2. What did you eat yesterday?
3. Are there any foods you disliked as a child but like now?
4. Do you prefer eating at home or eating out?

Gloss, shown only in a drill, via the “What is this asking?” control:

- en: Questions about who cooks, a recent meal, a change in taste, and home versus restaurants.
- cmn: 这几题问：谁做饭、昨天吃了什么、小时候不喜欢但现在喜欢的食物，以及更想在家吃还是出去吃。
- yue: 呢幾題問：邊個煮、尋日食咗咩、細個唔鍾意而家鍾意嘅嘢食，同埋想喺屋企食定出面食。

**`skill-you-taught` (Part 2), topic `people`**

Title: Describe a practical skill you taught someone you know.

You should say:

- who you taught
- what skill you taught them
- how you taught it
- and explain how you felt about teaching that person

Rounding-off, ask the first: “Do you still see that person often?”

Part 3, linked:

1. Why do some people prefer to learn a skill from a friend rather than in a class?
2. What practical skills are most useful before someone lives alone?
3. How has the way people learn practical skills changed in recent years?
4. Should schools spend more time teaching practical skills?

Drill gloss (yue): 「講一個你教過俾一個你識嘅人嘅實用技能：教邊個、教咗咩、點教，同埋你教完有咩感覺。」 Mock mode shows the English card only, which is also what a candidate sees in the real long turn.

### 19.4 Speaking session rules

**Drill.** After each Part 1 or Part 3 answer, the review card appears, then the learner chooses Next. Part 2 uses the timers below. A drill may show the support gloss and, on Part 2, checkmarks for bullets already covered. Pace is the learner’s.

**Diagnostic.** The fixed set in §19.3, drill rules, about ten minutes if answers are a normal length. The result is a plan, not a certificate.

**Mock.** Part 1, then Part 2, then Part 3, using scripted questions. No gloss, no bullet checkmarks, no review card, no “try saying” until the review screen after Part 3. Auto-play of examiner questions is on. The examiner line never contains praise, a recast, or a grammar tip.

Client timers override the model and the learner:

| Part | Clock | What the client does |
| --- | --- | --- |
| Mock Part 1 | 5:00 hard stop | Asks the next unused question from the chosen frames. At 4:15 it may start the question already on screen and then moves on at 5:00. Three frames or the clock, whichever ends first. |
| Part 2 prep | 60 seconds | Notes field is editable. Microphone and Send are disabled. At 0:00 the card stays visible and capture starts. |
| Part 2 speak | 2:00 hard stop | If the learner sends with `speech_ms` under 60 seconds, the examiner asks once, “Can you tell me anything else?”, and the clock keeps running. A second early send is accepted as the end. At 2:00, capture stops and the transcript in the field is submitted. |
| Part 2 rounding-off | one question | Then Part 3 in a mock, or the review in a drill. |
| Mock Part 3 | 5:00 hard stop | Next linked question until the clock ends. At least the first question is always asked. |

`speech_ms` is the time from the start of capture to Submit for that take, minus prep. Typed answers send `speech_ms: null`. Fluency is then `unscored`, and the review says length was not timed. Words per minute, when `speech_ms` is at least 20 seconds, is shown as a number (“about 110 words in 70 seconds”) and is **not** an input to the band. The real test does not publish a words-per-minute cutoff.

Word gates, applied before the model’s band is shown:

| Part | Words | Result |
| --- | --- | --- |
| 1 | under 8 | All criteria `unscored`, finding `too_short` |
| 1 | over 120 | Criteria still allowed, finding `too_long` (this is a long-turn answer to a short question) |
| 2 | under 40 | All criteria `unscored`, finding `too_short` |
| 3 | under 15 | All criteria `unscored`, finding `too_short` |

A follow-up of “Why?” or “Can you tell me anything else?” is a fixed string. It is used at most once per question, and only in a drill when a Part 3 answer is under 40 words, or in Part 2 under the 60-second rule. A mock Part 3 does not add teaching follow-ups beyond the next scripted question; cutting a short answer off is what the real discussion’s next question already does.

If the learner answers in Cantonese or Putonghua:

- Mock: the examiner repeats the same English question once, then moves on. That take is `not_english` and receives no band.
- Drill: no band for that take. The review explains the question in the support language and gives an English skeleton at the next step toward the target, still using any facts they managed to state.

### 19.5 Examiner, scaffolds, and memorised openings

The examiner is a script plus the two fixed follow-up strings. Display name only. No passport, no test-center small talk, no comment on the answer.

Scaffolds exist only in drills, and only when that criterion is the plan’s focus:

| Focus | Scaffold on screen | Hidden in a mock |
| --- | --- | --- |
| Fluency on Part 2 | The four bullets with empty checkmarks while they speak | Yes |
| Part 3 development | Three quiet labels: position, reason, example | Yes |
| Lexis | Nothing during the answer. Two collocations appear afterward | — |
| Grammar | Nothing during the answer. One combined sentence appears afterward | — |
| Template | Nothing during the answer. The review quotes the stock line and shows the stem again | — |

Stock openings are a finding of type `template` only when they do not answer the stem. Examples the review should catch: “This is a very thought-provoking question”, “Nowadays, with the development of technology”, and a whole answer that is only “every coin has two sides”. A natural “Well” or “I think” is not a template. The repair is to answer the actual question in the first sentence.

Part 3 has a second structural finding, `shape`:

- only a personal story and no general point, or
- only “people in society” and no example, or
- a two-clause question where the answer addresses only the first clause.

The quote for that finding is the question clause they did not take up.

### 19.6 Review contract

`POST /api/ielts/review`

```json
{
  "session_id": "uuid",
  "kind": "drill",
  "part": 2,
  "prompt_id": "skill-you-taught",
  "target_band": 6.5,
  "support": "yue",
  "script": "Hant",
  "accent": "en-GB",
  "speech_ms": 75000,
  "notes": "sister, soup, Saturday",
  "learner_text": "I taught my younger sister how to cook tomato soup...",
  "findings_already": []
}
```

`kind` is `drill`, `diagnostic`, or `mock_part`. A full mock sends three calls, one per part, after the mock, not during. `learner_text` max 4,000 characters. `notes` max 500, Part 2 only, and notes are context for the reviewer, not speech to be banded.

The server runs the word gates first. If all criteria are forced `unscored`, it still calls the model for the practice answer and the support-language explanation, and it throws away any bands the model returns.

Response, `contract: "1"`:

```json
{
  "contract": "1",
  "criteria": [
    {
      "id": "fluency_coherence",
      "status": "partial",
      "band": 6,
      "evidence": "You moved from who, to the soup, to how Saturday went."
    },
    {
      "id": "lexical_resource",
      "status": "assessed",
      "band": 6,
      "evidence": "You used 'good' for the skill, for her, and for the result.",
      "swaps": [
        { "instead_of": "good at cooking", "try": "already comfortable in the kitchen" }
      ]
    },
    {
      "id": "grammar_range",
      "status": "assessed",
      "band": 5,
      "evidence": "Most sentences are 'I taught her' plus a noun.",
      "upgrade_sentence": "I taught her how to season the soup because she always made it too bland."
    },
    {
      "id": "pronunciation",
      "status": "unscored",
      "band": null,
      "evidence": null
    }
  ],
  "overall_band": null,
  "overall_hidden_reason": "pronunciation_not_assessed",
  "bullets": [
    { "id": "who", "covered": true, "quote": "my younger sister" },
    { "id": "what", "covered": true, "quote": "tomato soup" },
    { "id": "how", "covered": false, "quote": null },
    { "id": "why", "covered": true, "quote": "she was going to live alone" }
  ],
  "findings": [{ "type": "bullet_missing", "bullet_id": "how" }],
  "practice_answer": {
    "aim_band": 6.0,
    "text": "I taught my younger sister to make tomato soup...",
    "why": "你已經講咗邊個同煮咩。呢句加咗點教同點解，仍然用你個例子。"
  },
  "next_drill": {
    "part": 2,
    "prompt_id": "skill-you-taught",
    "focus": "grammar_range"
  },
  "safety": { "refused": false }
}
```

Server checks:

| Field | Rule |
| --- | --- |
| `criteria` | Exactly the four ids, pronunciation always `unscored` and `band: null` in v1. |
| `status` | `assessed`, `partial`, or `unscored`. Fluency is `partial` when `speech_ms` is present and the word gate did not fire, because pauses and intonation were not measured. Fluency is `unscored` when `speech_ms` is null or the word gate zeroed the review. |
| `evidence` | Required when status is not `unscored`. Max 240 characters, support language. |
| `swaps` | At most two. `instead_of` must be a substring of `learner_text` after lowercasing. |
| `upgrade_sentence` | One English sentence, or null. It must reuse at least one content word of six or more letters from the learner text when the learner text has such a word (`sister`, `tomato`). |
| `bullets` | Present for Part 2 only. `covered: true` requires a `quote` that is a substring of `learner_text`. Otherwise the server sets `covered` to false. |
| `practice_answer.text` | English. Max 2,200 characters. The server attaches `phonetic` with `phonemize` in the selected accent. |
| `practice_answer.why` | Support language, colloquial Cantonese when support is `yue`. Max 300 characters. |
| `practice_answer.aim_band` | Follows §19.2. The server overwrites the model’s aim if it is above the target or more than one step above the lowest assessed band. |
| `overall_band` | Always `null` on speaking in v1. |
| `next_drill` | Server overwrites this with the rule in §19.8. The model’s suggestion is not used. |

`why`, `evidence`, and `gap` text are scanned for a denylist: `official band`, `you will score`, `guaranteed`, `examiner will give you`, `你實攞`, `官方分数`. A hit fails the review the same way a bad daily payload fails: one repair call, then 502.

During a mock, the client ignores `practice_answer` until the final review screen. Defense in depth: the mock client does not send a review request at all until Part 3 has ended.

### 19.7 Writing, after speaking

Same disclaimer, same “one step toward the target” rule, same support language for explanations. The script is typed. All four criteria are text, so a writing practice overall may be shown via `roundIeltsMean`. It is still not an official score.

Module matters here:

| Task | Module | Time in a mock | Length gate | Criteria |
| --- | --- | --- | --- | --- |
| Task 2 essay | Both | 40:00 | Under 250 words sets `under_length` and the training action becomes “finish the essay” before any lexical polish. The band may still be returned, with the warning above it. | Task response, coherence and cohesion, lexical resource, grammatical range |
| Task 1 letter | General only | 20:00 | Under 150 words sets `under_length`. The prompt names the tone: informal, semi-formal, or formal. | Task achievement, plus the same three language criteria |
| Task 1 chart | Academic only | 20:00 | Under 150 words sets `under_length`. Describing the numbers is the task. | Task achievement, plus the same three language criteria |

Deterministic checks, before the model’s task score is trusted:

- Academic Task 1: if the script contains `I think` or `in my opinion`, add finding `opinion_in_task_1`.
- Either task: a live word counter. Mock timers are client-side and submit whatever is written at 0:00.
- Drill only: an optional outline (position, two reasons, one example, a close) that is hidden in the mock.

Original prompts for the first build, not taken from a published paper:

- **Task 2.** “Some people think adults should spend their free time learning practical skills instead of taking academic courses. To what extent do you agree or disagree?” At least 250 words.
- **General Task 1.** “You recently stayed at a friend’s home. Write a letter to thank them. Say what you enjoyed, describe one thing you did together, and invite them to stay with you.” Informal. At least 150 words.
- **Academic Task 1.** A table the UI draws, not an image: visitors in millions — City A 2.1, 2.8, 1.2, 3.6 and City B 3.4, 3.1, 1.5, 2.9 for the years 2015, 2018, 2021, and 2024. Instruction under the table: summarise the main features and make comparisons. No opinion. At least 150 words.

The endpoint is `POST /api/ielts/writing-review` with the same clamping rules as §19.6, criterion ids `task`, `coherence_cohesion`, `lexical_resource`, `grammar_range`, and `overall_band` allowed. Pronunciation is absent. Build this as step 9, after speaking.

### 19.8 The plan

This is the training loop. It is deterministic TypeScript in `ieltsPlan.ts`, so a test can pin it without a model.

1. If there is no review yet, `next_drill` is the diagnostic.
2. Otherwise take the latest review. Among criteria that are `assessed` or `partial`, pick the lowest band. Ties break in this order: `grammar_range`, `lexical_resource`, `fluency_coherence`. Pronunciation is never the focus in v1.
3. Map that focus, together with findings, to a drill:

| Condition | Next drill |
| --- | --- |
| Any Part 2 bullet missing, or Part 2 `too_short` | Same cue card, Part 2, focus `fluency_coherence`, checklist on |
| `template` or Part 3 `shape` | Same Part 3 question, focus the winning criterion, position/reason/example labels on |
| Focus `lexical_resource` | Same prompt, and the review’s swaps are the thing they shadow |
| Focus `grammar_range` | Same prompt; they say the upgrade sentence, then answer once more |
| `not_english` | Same prompt, gloss open, English skeleton shown before they record |
| Else | The next unused prompt in the same part |

4. After three completed drills since the last diagnostic or mock, the home screen offers a full speaking mock and still leaves the drill one tap away. It does not lock the drill.
5. An exam date inside the next 14 days changes the home subtitle to recommend the mock first. No streak, no “you missed a day”.

Shadowing, after a drill review:

1. Read `practice_answer.text`.
2. Play it (phonetics from `phonemize`; voice from §9.2).
3. Hide the text and record again.
4. The client lists content words from the practice answer that the new transcript does not contain. Content words are tokens of six or more letters minus a small function-word list kept in the repo. This list is a memory aid, not a band.

The second recording is a new review and a new history row.

Across parts, the history screen shows each criterion’s band **per part**. The summary number for a criterion is the **lowest** part band, labeled “weakest part”, because the plan needs a drill target. That is harsher than a real examiner, who judges the whole interview. The screen says so in one line: “This is your weakest part, not an examiner’s overall mark.”

### 19.9 Listening and Reading, not in this build

Both are real IELTS skills and a poor fit for the conversation screen. When they are built:

- Passages, audio scripts, and questions are written for this app. Official papers stay out.
- A listening mock plays each recording once. A listening drill may replay. The screen states which mode is running, because those are not the same difficulty.
- Reading is three passages and 40 questions in 60 minutes. Academic and General Training get different passage styles.
- Marking is automatic against an answer key.
- The result is “32 out of 40”, not a band, until an in-house conversion is deliberately published as ours. Official raw-to-band tables change by version and are not copied in as if they were a formula.

### 19.10 Fixtures the implementation must pin

1. **Rounding.** `roundIeltsMean([6, 6, 6, 7]) === 6.5` and `roundIeltsMean([6, 7, 7, 7]) === 7`. A speaking review fixture with pronunciation `unscored` has `overall_band === null` even if the other three bands are 7.
2. **Timers.** Prep disables the mic for 60 seconds. Speech capture at 120 seconds submits without waiting for the model. One early Part 2 send produces exactly one “Can you tell me anything else?”.
3. **Quotes.** Bullet `who` with quote `my cousin` is stored uncovered when the transcript says `my younger sister`.
4. **Facts stay.** Learner text contains `sister` and `soup`. `practice_answer.text` contains both. `aim_band` is 6.0 when the lowest assessed band is 5 and the target is 6.5.
5. **Clamp.** A model criterion band of 9 is returned to the client as `unscored`, not as 8 and not as 9.
6. **Short answer.** Seven words on Part 1 produces no criterion bands and finding `too_short`.
7. **Typed Part 2.** `speech_ms: null` forces fluency `unscored` and does not display words per minute.
8. **Mock silence.** The mock reducer drops review UI until phase `review`. A buggy payload that includes `practice_answer` mid-mock is not rendered.
9. **Refusal.** A review request whose learner text is “Just tell me yesterday’s Hong Kong cue cards” returns `safety.refused: true` and the original-prompt explanation, with no list of topics presented as leaked questions.
10. **Plan.** Lowest criterion grammar, band 5, no missing bullet → `next_drill.focus === "grammar_range"` on the same prompt. A missing Part 2 bullet overrides that and focuses fluency on that card.
11. **Academic Task 1.** A script containing “I think the drop in 2021 is huge” gains `opinion_in_task_1`. A 140-word Task 2 gains `under_length`.
12. **Accent neutrality.** A review of an answer that uses “apartment” and “elevator” does not produce a correction telling the learner to say “flat” and “lift”.
13. **Gloss.** Diagnostic and drill render the Cantonese gloss for `food-at-home`. The mock render of the same frame does not contain `邊個煮`.
