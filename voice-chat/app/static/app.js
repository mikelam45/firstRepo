import { IllustratedPortrait, Portrait, englishVisemes, pinyinVisemes } from "./face.js?v=20261023-chloe-voice";
import { collectTranscript, recognitionLanguage, transcriptPiece } from "./transcript.js";

const I18N = {
  en: {
    drill: "Today's IELTS drill",
    mock: "Full speaking mock",
    daily: "Daily talk",
    teacher: "English teacher",
    teacherHint: "Grammar, words, and phrases",
    correctionMode: "Correction",
    conversationMode: "Conversation",
    history: "History",
    settings: "Settings",
    back: "Back",
    change: "Change partner",
    placeholder: "Type, or tap the mic",
    send: "Send",
    play: "Play line",
    listening: "Listening",
    stopped: "Stopped",
    trySaying: "Try saying",
    howRead: "How it is read",
    why: "Why",
    praise: "Praise",
    practiceAgain: "Practice again",
    notAssessed: "Not assessed",
    disclaimer: "Practice estimate only. This is not an IELTS result, and this app is not an IELTS test center.",
    noBand: "Pronunciation was not assessed, so there is no speaking band.",
    nowTalking: "Now talking with",
    micBlocked: "The browser blocked the microphone. You can type instead.",
    recNetwork: "Recognition needs a connection.",
    noMic: "No microphone found.",
    noCantoneseMic: "Cantonese recognition isn’t available in this browser. Type in Cantonese.",
    noVoice: "No matching voice is installed on this device.",
    noCantoneseVoice: "No Cantonese voice is installed, so this line stays silent instead of using Mandarin. The mouth can still move.",
    noSynth: "This browser has no speech synthesis. Typing still works.",
    micInsecure: "The browser blocks speech recognition on this address. Open",
    micUnsupported: "This browser has no speech recognition. You can type instead.",
    micError: "Voice input failed ({code}). You can type instead.",
    micAborted: "Listening stopped.",
    noSpeech: "No speech heard. Tap the microphone, speak, then tap it again. The text stays in the box; Enter sends it.",
    adult: "LingoCoach is for adult learners.",
    privacy: "Transcripts stay on this device and are sent as text for each turn. Browser recognition may send audio to the browser vendor. This server does not keep audio.",
    historyLoss: "Clearing this browser’s data deletes history. There is no account.",
    tooMany: "Too many turns. Wait a moment.",
    retry: "Retry",
    coachUnavailable: "The coach is unavailable.",
    network: "Network error.",
    showTranslation: "Show translation",
    whatAsking: "What is this asking?",
    goalMet: "Goal met",
    fixture: "Offline examples — this server has no OpenRouter key.",
    notes: "Notes",
    next: "Next",
    covered: "Covered",
    notYet: "Not yet",
    startNew: "Start a new practice? This chat stays in History.",
    yes: "Start new",
    cancel: "Cancel",
    close: "Close",
    womenMen: "All 27. Chloe teaches English. Celine takes the café order.",
    corrGrammar: "Grammar",
    corrWord: "Wrong word",
    corrPhrase: "Wrong phrase",
    corrRegister: "Register",
    corrCompleteness: "Missing piece",
    corrMismatch: "Language",
    illustrated: "Illustrated portrait. The mouth still moves with the line.",
    mesh: "Photo portrait.",
    examSoon: "Your date is close. A full mock is the better first tap. The drill stays available.",
    mockReady: "You have finished three drills. A full mock is one tap away.",
    weak: "This is your weakest part, not an examiner’s overall mark.",
    prep: "60 seconds to prepare. The microphone stays off.",
    speaking: "Speaking",
    part: "Part",
    diagnostic: "Diagnostic",
    review: "Review",
    practiceEstimate: "Practice estimate",
    target: "Target language",
    support: "Support language",
    level: "Level",
    script: "Han script",
    accent: "English accent",
    autoplay: "Play lines automatically",
    pinyin: "Pinyin tones",
    marks: "Tone marks",
    numbers: "Numbers",
    module: "IELTS module",
    band: "Target band",
    exam: "Exam date (optional)",
    track: "Track",
    save: "Save",
    emptyHistory: "No saved sessions yet.",
    again: "Practice again",
    begin: "Beginner",
    intermediate: "Intermediate",
    advanced: "Advanced",
    waiting: "Thinking…",
    goal: "Goal",
    partner: "Partner",
    age: "27",
    orCheck: "OpenRouter LLM connectivity check",
    orChecking: "Checking…",
    orConnected: "Connected",
    orNoKey: "Not connected. No OpenRouter key. Put it in /Users/mikelam/firstRepo/openrouter_key/.env_voice_chat and restart ./run-local.sh from voice-chat.",
    orRejected: "Not connected. Wrong key. OpenRouter rejected it. The key is not shown.",
    orUnreachable: "Not connected. Connection error. This server cannot reach OpenRouter. Check the network, then press Check again.",
    orRecheck: "Check",
  },
  cmn: {
    drill: "今天的雅思口语练习",
    mock: "完整口语模拟",
    daily: "日常对话",
    teacher: "英语老师",
    teacherHint: "语法、用词和短语",
    correctionMode: "纠错模式",
    conversationMode: "对话模式",
    history: "历史",
    settings: "设置",
    back: "返回",
    change: "换一个人",
    placeholder: "打字，或点一下麦克风",
    send: "发送",
    play: "播放这句",
    listening: "正在听",
    stopped: "已停止",
    trySaying: "可以这样说",
    howRead: "这样读",
    why: "为什么",
    praise: "做得好",
    practiceAgain: "再练一次",
    notAssessed: "未评估",
    disclaimer: "仅为练习估计。这不是雅思成绩，本应用也不是雅思考试中心。",
    noBand: "发音未作评估，所以没有口语总分。",
    nowTalking: "现在和",
    micBlocked: "浏览器阻止了麦克风。你可以打字。",
    recNetwork: "语音识别需要网络。",
    noMic: "没有找到麦克风。",
    noCantoneseMic: "这个浏览器不能识别粤语。请用粤语打字。",
    noVoice: "这台设备没有对应的语音。",
    noCantoneseVoice: "这台设备没有粤语语音，所以这句不会用普通话读出来。嘴仍然可以动。",
    noSynth: "这个浏览器不能朗读。打字仍然可以用。",
    micInsecure: "这个地址不能用语音识别，因为它不是本机安全页面。请打开",
    micUnsupported: "这个浏览器没有语音识别。你可以打字。",
    micError: "语音输入失败（{code}）。你可以打字。",
    micAborted: "已经停止听了。",
    noSpeech: "没有听到说话。点一下麦克风，说完再点一下。文字会留在框里，按回车送出。",
    adult: "LingoCoach 面向成年学习者。",
    privacy: "对话留在这台设备上，每次只把文字发给模型。浏览器识别可能会把声音发给浏览器厂商。这个服务器不保存录音。",
    historyLoss: "清除浏览器数据会丢掉历史。没有账号。",
    tooMany: "轮次太密了，等一会儿。",
    retry: "重试",
    coachUnavailable: "教练暂时不可用。",
    network: "网络错误。",
    showTranslation: "显示翻译",
    whatAsking: "这题在问什么？",
    goalMet: "目标完成",
    fixture: "离线例句——这台服务器没有 OpenRouter 密钥。",
    notes: "笔记",
    next: "下一题",
    covered: "已覆盖",
    notYet: "还没有",
    startNew: "开始一次新的练习？这段对话会留在历史里。",
    yes: "开始新的",
    cancel: "取消",
    close: "关闭",
    womenMen: "全部 27 岁。Chloe 是英语老师。Celine 是咖啡店服务员。",
    corrGrammar: "语法",
    corrWord: "用词",
    corrPhrase: "短语",
    corrRegister: "说法",
    corrCompleteness: "还缺信息",
    corrMismatch: "语言",
    illustrated: "插画肖像。说话时嘴会动。",
    mesh: "照片肖像。",
    examSoon: "考试日期很近。可以先做完整模拟，练习仍然可以点。",
    mockReady: "你已经完成三次练习。完整模拟就在旁边。",
    weak: "这是你最弱的一部分，不是考官的总分。",
    prep: "准备 60 秒。麦克风先关掉。",
    speaking: "正在说",
    part: "第",
    diagnostic: "诊断",
    review: "复习",
    practiceEstimate: "练习估计",
    target: "目标语言",
    support: "辅助语言",
    level: "程度",
    script: "汉字",
    accent: "英语口音",
    autoplay: "自动播放",
    pinyin: "拼音声调",
    marks: "声调符号",
    numbers: "数字",
    module: "雅思类别",
    band: "目标分数",
    exam: "考试日期（可选）",
    track: "路线",
    save: "保存",
    emptyHistory: "还没有保存的练习。",
    again: "再练一次",
    begin: "初级",
    intermediate: "中级",
    advanced: "高级",
    waiting: "想一下…",
    goal: "目标",
    partner: "练习伙伴",
    age: "27",
    orCheck: "OpenRouter 大模型连通检查",
    orChecking: "正在检查…",
    orConnected: "已连接",
    orNoKey: "未连接。没有 OpenRouter 密钥。请把它放在 /Users/mikelam/firstRepo/openrouter_key/.env_voice_chat，然后在 voice-chat 里重新运行 ./run-local.sh。",
    orRejected: "未连接。密钥不对。OpenRouter 拒绝了它。密钥不会显示。",
    orUnreachable: "未连接。连接错误。这台服务器连不上 OpenRouter。请检查网络，然后再按检查。",
    orRecheck: "检查",
  },
  yue: {
    drill: "今日嘅雅思口試練習",
    mock: "全套口試模擬",
    daily: "日常對話",
    teacher: "英文老師",
    teacherHint: "文法、用詞同短語",
    correctionMode: "糾錯模式",
    conversationMode: "對話模式",
    history: "紀錄",
    settings: "設定",
    back: "返回",
    change: "轉人",
    placeholder: "打字，或者點一下個咪",
    send: "送出",
    play: "播呢句",
    listening: "聽緊",
    stopped: "停咗",
    trySaying: "可以咁講",
    howRead: "點讀",
    why: "點解",
    praise: "做得好",
    practiceAgain: "再練一次",
    notAssessed: "未評估",
    disclaimer: "只係練習估計。呢個唔係雅思成績，呢個 app 亦都唔係雅思考試中心。",
    noBand: "發音未評估，所以冇口語總分。",
    nowTalking: "而家同",
    micBlocked: "個瀏覽器擋咗個咪。你可以打字。",
    recNetwork: "語音識別要有網絡。",
    noMic: "搵唔到咪。",
    noCantoneseMic: "呢個瀏覽器認唔到廣東話。請打廣東話。",
    noVoice: "呢部機冇對應嘅語音。",
    noCantoneseVoice: "呢部機冇廣東話語音，所以呢句唔會用普通話讀出嚟。個嘴仍然可以郁。",
    noSynth: "呢個瀏覽器唔識朗讀。打字仍然用到。",
    micInsecure: "呢個地址用唔到語音識別，因為佢唔係本機安全頁面。請打開",
    micUnsupported: "呢個瀏覽器冇語音識別。你可以打字。",
    micError: "語音輸入失敗（{code}）。你可以打字。",
    micAborted: "停咗聽。",
    noSpeech: "聽唔到你講。點一下個咪，講完再點一下。文字會留喺格入面，撳 Enter 送出。",
    adult: "LingoCoach 係俾成年學習者用。",
    privacy: "對話留喺呢部機。每次只係將文字送去模型。瀏覽器識別可能會將聲音交俾瀏覽器公司。呢個伺服器唔會留低錄音。",
    historyLoss: "清咗瀏覽器資料就冇紀錄。冇帳戶。",
    tooMany: "轉得太密，等一陣。",
    retry: "再試",
    coachUnavailable: "教練暫時用唔到。",
    network: "網絡錯誤。",
    showTranslation: "顯示翻譯",
    whatAsking: "呢題問咩？",
    goalMet: "目標完成",
    fixture: "離線例句——呢部伺服器冇 OpenRouter 金鑰。",
    notes: "筆記",
    next: "下一題",
    covered: "覆蓋到",
    notYet: "未覆蓋",
    startNew: "開始一次新練習？呢段對話會留喺紀錄。",
    yes: "開始新嘅",
    cancel: "取消",
    close: "關閉",
    womenMen: "全部 27 歲。Chloe 係英文老師。Celine 係茶餐廳侍應。",
    corrGrammar: "文法",
    corrWord: "用詞",
    corrPhrase: "短語",
    corrRegister: "講法",
    corrCompleteness: "仲缺資料",
    corrMismatch: "語言",
    illustrated: "插畫肖像。講嘢嗰陣個嘴會郁。",
    mesh: "相片肖像。",
    examSoon: "考試日子近。可以先做全套模擬，練習仍然撳到。",
    mockReady: "你完成咗三次練習。全套模擬喺隔離。",
    weak: "呢個係你最弱嘅部分，唔係考官嘅總分。",
    prep: "準備 60 秒。個咪暫時關掉。",
    speaking: "講緊",
    part: "第",
    diagnostic: "診斷",
    review: "溫習",
    practiceEstimate: "練習估計",
    target: "目標語言",
    support: "輔助語言",
    level: "程度",
    script: "漢字",
    accent: "英語口音",
    autoplay: "自動播放",
    pinyin: "拼音聲調",
    marks: "聲調符號",
    numbers: "數字",
    module: "雅思類別",
    band: "目標分數",
    exam: "考試日期（可選）",
    track: "路線",
    save: "儲存",
    emptyHistory: "未有儲存嘅練習。",
    again: "再練一次",
    begin: "初級",
    intermediate: "中級",
    advanced: "高級",
    waiting: "諗緊…",
    goal: "目標",
    partner: "練習夥伴",
    age: "27",
    orCheck: "OpenRouter 大模型連線檢查",
    orChecking: "檢查緊…",
    orConnected: "已連線",
    orNoKey: "未連線。冇 OpenRouter 金鑰。請放喺 /Users/mikelam/firstRepo/openrouter_key/.env_voice_chat，然後喺 voice-chat 重新行 ./run-local.sh。",
    orRejected: "未連線。金鑰唔啱。OpenRouter 拒絕咗。金鑰唔會顯示。",
    orUnreachable: "未連線。連線錯誤。呢部伺服器連唔到 OpenRouter。請檢查網絡，然後再撳檢查。",
    orRecheck: "檢查",
  },
};

const app = document.querySelector("#app");
const state = {
  screen: "home",
  catalogue: null,
  settings: loadSettings(),
  sheet: null,
  confirm: null,
  notice: "",
  provider: null,
  daily: null,
  ielts: null,
  history: [],
  teacherMode: loadTeacherMode(),
  micHidden: false,
  cantoneseMicHidden: false,
  micMessage: "",
  lastBody: null,
  speaking: null,
  llm: { phase: "checking", connected: false, reason: "" },
};

let face = null;
let mountToken = 0;
let lastFrame = performance.now();
let voices = [];
let sessionRate = null;
let recognizer = null;
let listening = false;
let draftBeforeMic = "";
let composerDraft = "";
let speakToken = 0;
let speakTimer = 0;
let mouthTimer = 0;
let activeUtterance = null;
let micEngineStarted = false;
let micStopRequested = false;
let micHeard = false;
let acceptMicText = false;
let micHoldTimer = 0;
let micHolding = false;
let micGestureId = null;
let micSuppressClick = false;
let micStartTimer = 0;
let micDownAt = 0;
let llmToken = 0;
let threadUserScrolled = false;
let ignoreThreadScrollUntil = 0;

function t(key) {
  const pack = I18N[state.settings.support] || I18N.en;
  return pack[key] || I18N.en[key] || key;
}

function defaults() {
  return {
    track: "ielts",
    partner: "amelia",
    target: "en",
    support: "yue",
    level: "beginner",
    script: "Hant",
    accent: "en-GB",
    autoplay: true,
    pinyin_tone: "mark",
    module: "academic",
    target_band: 6.5,
    exam_date: "",
  };
}

function loadSettings() {
  const base = defaults();
  try {
    const v3 = localStorage.getItem("lingocoach.settings.v3");
    if (v3) {
      const data = { ...base, ...JSON.parse(v3) };
      if (data.partner === "nora") data.partner = "chloe";
      return data;
    }
    const v2 = localStorage.getItem("lingocoach.settings.v2");
    if (v2) {
      const data = { ...base, ...JSON.parse(v2), partner: "amelia" };
      localStorage.setItem("lingocoach.settings.v3", JSON.stringify(data));
      return data;
    }
    const v1 = localStorage.getItem("lingocoach.settings.v1");
    if (v1) {
      const data = { ...base, ...JSON.parse(v1), partner: "amelia", track: "ielts", target_band: 6.5 };
      localStorage.setItem("lingocoach.settings.v3", JSON.stringify(data));
      return data;
    }
  } catch (err) {
    /* keep defaults */
  }
  return base;
}

function saveSettings() {
  localStorage.setItem("lingocoach.settings.v3", JSON.stringify(state.settings));
}

function loadTeacherMode() {
  try {
    const v = localStorage.getItem("lingocoach.teacher.mode.v1");
    if (v === "correction" || v === "conversation") return v;
  } catch (err) {
    /* keep default */
  }
  return "correction";
}

function saveTeacherMode() {
  localStorage.setItem("lingocoach.teacher.mode.v1", state.teacherMode);
}

function clientId() {
  let id = localStorage.getItem("lingocoach.client");
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : `c-${Date.now()}`;
    localStorage.setItem("lingocoach.client", id);
  }
  return id;
}

function uuid() {
  return crypto.randomUUID ? crypto.randomUUID() : `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function partner() {
  const list = state.catalogue?.partners || [];
  return list.find((item) => item.id === state.settings.partner) || list[0];
}

function activePartner() {
  const list = state.catalogue?.partners || [];
  const id = state.screen === "daily" && state.daily?.partner_id ? state.daily.partner_id : state.settings.partner;
  return list.find((item) => item.id === id) || partner();
}

function selectedPartnerId() {
  if (state.screen === "daily" && state.daily?.partner_id) return state.daily.partner_id;
  return state.settings.partner;
}

function roleLabel(item) {
  if (!item?.role) return "";
  const support = state.settings.support;
  return item.role[support] || item.role.en || "";
}

function practiceTarget() {
  if (state.screen === "ielts") return "en";
  if (state.daily?.scenario_id === "english-teacher") return "en";
  return state.settings.target || "en";
}

const TEACHER_ID = "chloe";
const CAFE_ID = "celine";
const CAFE_SCENE = "hk-cha-chaan-teng";

function scenario() {
  const list = state.catalogue?.scenarios || [];
  return list.find((item) => item.id === state.daily?.scenario_id) || list[0];
}

function promptById(id) {
  return (state.catalogue?.ielts || []).find((item) => item.id === id);
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render() {
  app.innerHTML = `<div class="phone">${view()}${openRouterBar()}${sheet()}</div><p id="live" class="sr" aria-live="polite"></p>`;
  mountFace();
  scrollThread(false);
}

function scrollThread(force = false) {
  // Wait until the browser has laid out the newly rendered content; otherwise
  // scrollHeight is stale and the thread jumps back to the top (oldest).
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const thread = document.querySelector("#thread") || document.querySelector(".thread");
      if (!thread) return;
      const nearBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight <= 120;
      if (force || !threadUserScrolled || nearBottom) {
        ignoreThreadScrollUntil = performance.now() + (force ? 80 : 600);
        thread.scrollTop = thread.scrollHeight;
      }
    });
  });
}

function view() {
  if (!state.catalogue) return `<main class="home"><p>${esc(t("waiting"))}</p></main>`;
  if (state.screen === "history") return historyView();
  if (state.screen === "daily") return dailyView();
  if (state.screen === "ielts") return ieltsView();
  return homeView();
}

function homeView() {
  const who = partner();
  const plan = loadPlan();
  const soon = examSoon();
  return `
    <header class="top">
      <div class="mark">LingoCoach</div>
      <div class="grow"></div>
      <button class="icon-btn" type="button" data-act="history">${esc(t("history"))}</button>
      <button class="icon-btn" type="button" data-act="settings" aria-label="${esc(t("settings"))}">⚙</button>
    </header>
    <main class="home">
      <div class="stage">
        <canvas id="face" class="face" width="480" height="640" aria-label="${esc(who.name)}, ${esc(who.city)}, 27"></canvas>
        <div>
          <strong>${esc(who.name)}</strong>
          <div class="muted">${esc(who.city)} · ${esc(t("age"))}${roleLabel(who) ? ` · ${esc(roleLabel(who))}` : ""}</div>
          <button class="ghost" type="button" data-act="partners">${esc(t("change"))}</button>
        </div>
      </div>
      ${soon ? `<p class="banner">${esc(t("examSoon"))}</p>` : ""}
      ${plan.drillsSince >= 3 ? `<p class="banner">${esc(t("mockReady"))}</p>` : ""}
      ${state.provider === "fixture" ? `<p class="banner">${esc(t("fixture"))}</p>` : ""}
      <div class="choices">
        <button class="choice" type="button" data-act="drill"><strong>${esc(t("drill"))}</strong><span class="muted">${esc(plan.label || t("diagnostic"))}</span></button>
        <button class="choice" type="button" data-act="mock"><strong>${esc(t("mock"))}</strong><span class="muted">Part 1 · Part 2 · Part 3</span></button>
        <button class="choice" type="button" data-act="daily"><strong>${esc(t("daily"))}</strong></button>
        <button class="choice" type="button" data-act="teacher"><strong>${esc(t("teacher"))}</strong><span class="muted">${esc(t("teacherHint"))}</span></button>
      </div>
      <p class="small muted">${esc(t("disclaimer"))}</p>
      <p class="small muted">${esc(t("adult"))}</p>
    </main>`;
}

function dailyView() {
  const sc = scenario();
  const who = activePartner();
  const support = state.settings.support;
  const title = sc.title[support] || sc.title.en;
  const goal = sc.goal[support] || sc.goal.en;
  const teacher = sc.id === "english-teacher";
  const ended = teacher ? state.daily.cap_reached : (state.daily.goal === "met" || state.daily.cap_reached);
  const scenes = (state.catalogue.scenarios || []).filter((item) => item.id !== "english-teacher");
  return `
    <header class="top">
      <button class="icon-btn" type="button" data-act="home">${esc(t("back"))}</button>
      <div class="grow"><h1>${esc(who.name)}</h1><div class="small muted">${esc(title)}</div></div>
      <button class="icon-btn" type="button" data-act="settings">⚙</button>
    </header>
    ${teacher ? "" : `<div class="chips" role="tablist">
      ${scenes.map((item) => `<button class="chip" type="button" data-act="scenario" data-id="${esc(item.id)}" aria-pressed="${item.id === sc.id}">${esc(item.title[support] || item.title.en)}</button>`).join("")}
    </div>`}
    <p class="goal">${esc(t("goal"))}: ${esc(goal)}${state.daily.goal === "met" ? ` · ${esc(t("goalMet"))}` : ""}</p>
    ${teacher ? modeToggleHtml() : ""}
    ${state.provider === "fixture" ? `<p class="banner">${esc(t("fixture"))}</p>` : ""}
    <div class="stage large"><canvas id="face" class="face" width="480" height="640" aria-label="${esc(who.name)}, ${esc(who.city)}, 27"></canvas></div>
    <div class="row" style="padding:0 16px 8px">
      <strong>${esc(who.name)}</strong>
      <span class="muted">${esc(who.city)} · 27${roleLabel(who) ? ` · ${esc(roleLabel(who))}` : ""}</span>
      <button class="ghost" type="button" data-act="partners">${esc(t("change"))}</button>
    </div>
    <div class="thread" id="thread">${(state.daily.bubbles || []).map(bubbleHtml).join("")}</div>
    ${ended ? `<div class="composer"><button class="primary" type="button" data-act="again">${esc(t("practiceAgain"))}</button></div>` : composerHtml()}
    ${state.notice ? `<p class="banner error">${esc(state.notice)}</p>` : ""}`;
}

function bubbleHtml(bubble, index) {
  if (bubble.role === "learner") {
    return `<article class="bubble learner"><div class="said"><div class="row"><p class="text grow">${esc(bubble.text)}</p><button class="icon-btn speak" type="button" data-act="speak" data-index="${index}" aria-label="${esc(t("play"))}">▶</button></div></div>${coachHtml(bubble, index)}</article>`;
  }
  const who = (state.catalogue.partners || []).find((item) => item.id === bubble.partner_id);
  const lineTarget = state.daily?.scenario_id === "english-teacher" ? "en" : state.settings.target;
  const showTranslation = state.settings.support !== lineTarget && bubble.translation;
  let translation = "";
  if (showTranslation && state.settings.level === "beginner") translation = `<p>${esc(bubble.translation)}</p>`;
  else if (showTranslation && state.settings.level === "intermediate") translation = `<details><summary>${esc(t("showTranslation"))}</summary><p>${esc(bubble.translation)}</p></details>`;
  else if (showTranslation) translation = bubble.showTranslation ? `<p>${esc(bubble.translation)}</p>` : `<button class="ghost" type="button" data-act="translate" data-index="${index}">${esc(t("showTranslation"))}</button>`;
  const phonetic = phoneticHtml(bubble);
  return `<article class="bubble character"><div class="who">${esc(who?.name || "")}</div><div class="panel"><div class="row"><p class="text grow">${esc(bubble.text)}</p><button class="icon-btn speak" type="button" data-act="speak" data-index="${index}" aria-label="${esc(t("play"))}">▶</button></div>${phonetic}${translation}</div></article>`;
}

function phoneticHtml(bubble) {
  if (!bubble.phonetic) return "";
  const label = bubble.phonetic_system === "jyutping" ? "Jyutping" : bubble.phonetic_system === "pinyin" ? "Pinyin" : bubble.phonetic_system === "ipa-ga" ? "IPA · GA" : "IPA · RP";
  const amb = new Set((bubble.syllables || []).filter((item) => item.ambiguous).map((item) => item.reading));
  const html = esc(bubble.phonetic).split(" ").map((token) => amb.has(token.replace(/^\/|\/$/g, "")) ? `<span class="amb" title="${esc(token)}">${token}</span>` : token).join(" ");
  return `<p class="phonetic"><span class="muted">${esc(label)}</span> ${html}</p>`;
}

function modeToggleHtml() {
  const mode = state.teacherMode || "correction";
  return `<div class="mode-toggle" role="group" aria-label="${esc(`${t("correctionMode")} / ${t("conversationMode")}`)}">
    <button class="mode-btn${mode === "correction" ? " active" : ""}" type="button" data-act="teacher-mode" data-mode="correction">${esc(t("correctionMode"))}</button>
    <button class="mode-btn${mode === "conversation" ? " active" : ""}" type="button" data-act="teacher-mode" data-mode="conversation">${esc(t("conversationMode"))}</button>
  </div>`;
}

function correctionLabel(type) {
  const key = {
    grammar: "corrGrammar",
    vocabulary: "corrWord",
    phrase: "corrPhrase",
    register: "corrRegister",
    completeness: "corrCompleteness",
    mismatch: "corrMismatch",
  }[type];
  return key ? t(key) : type;
}

function coachHtml(bubble) {
  if (bubble.pending) return `<div class="coach">${esc(t("waiting"))}</div>`;
  if (bubble.error) return `<div class="coach"><p class="error">${esc(bubble.error)}</p><button class="ghost" type="button" data-act="retry">${esc(t("retry"))}</button></div>`;
  const coaching = bubble.coaching;
  if (!coaching) return "";
  const bits = [];
  const corrections = coaching.corrections || [];
  if (!corrections.length && coaching.praise) bits.push(`<p><strong>${esc(t("praise"))}.</strong> ${esc(coaching.praise)}</p>`);
  for (const item of corrections) {
    bits.push(`<p><strong>${esc(correctionLabel(item.type))}.</strong> <span class="quote">“${esc(item.quote)}”</span></p>`);
    if (item.why) bits.push(`<p><strong>${esc(t("why"))}.</strong> ${esc(item.why)}</p>`);
  }
  if (coaching.suggested_reply) {
    bits.push(`<p><strong>${esc(t("trySaying"))}</strong></p><p>${esc(coaching.suggested_reply)}</p>`);
    if (coaching.suggested_reply_phonetic) bits.push(`<p class="phonetic">${esc(coaching.suggested_reply_phonetic)}</p>`);
    bits.push(`<button class="ghost" type="button" data-act="speak-suggest" aria-label="${esc(t("play"))}">▶</button>`);
  }
  if (coaching.reading_hints?.length) {
    bits.push(`<p><strong>${esc(t("howRead"))}</strong></p>`);
    for (const hint of coaching.reading_hints) bits.push(`<p>${esc(hint.term)} — ${esc(hint.note)}</p>`);
  }
  if (corrections.length && coaching.praise) bits.push(`<p><strong>${esc(t("praise"))}.</strong> ${esc(coaching.praise)}</p>`);
  if (!bits.length) return "";
  return `<div class="coach">${bits.join("")}</div>`;
}

function composerHtml() {
  const block = micBlock();
  const showMic = block === "" || block === "insecure";
  const off = block === "insecure";
  const live = listening && !off;
  const mic = showMic
    ? `<button class="mic${live ? " live" : ""}" id="mic" type="button"${off ? " disabled" : ""} aria-pressed="${live ? "true" : "false"}" aria-label="${esc(live ? `${t("listening")}. Stop` : t("placeholder"))}">${live ? esc(t("listening")) : "🎤"}</button>`
    : "";
  return `<form class="composer" id="composer">
    ${mic}
    <textarea id="field" rows="1" placeholder="${esc(t("placeholder"))}" aria-label="${esc(t("placeholder"))}">${esc(composerDraft)}</textarea>
    <button class="icon-btn speak" type="button" data-act="speak-draft" aria-label="${esc(t("play"))}">▶</button>
    <button class="send" type="submit">${esc(t("send"))}</button>
  </form>
  ${statusHtml()}`;
}

function ieltsView() {
  const session = state.ielts;
  const who = partner();
  const gloss = session.kind === "mock" ? "" : session.gloss || "";
  const review = session.phase === "review" || session.phase === "done" ? reviewHtml(session.review) : "";
  const cue = cueHtml(session);
  return `
    <header class="top">
      <button class="icon-btn" type="button" data-act="home">${esc(t("back"))}</button>
      <div class="grow"><h1>${esc(who.name)}</h1><div class="small muted">${esc(t("part"))} ${esc(session.part)} · ${esc(session.kind)}</div></div>
      <div class="clock" id="clock">${esc(clockText())}</div>
    </header>
    <div class="stage large"><canvas id="face" class="face" width="480" height="640" aria-label="${esc(who.name)}, 27"></canvas></div>
    <div class="row" style="padding:0 16px"><strong>${esc(who.name)}</strong><span class="muted">${esc(who.city)} · 27</span><button class="ghost" type="button" data-act="partners" ${session.kind === "mock" && (session.phase === "part2_prep" || session.phase === "part2_speak") ? "disabled" : ""}>${esc(t("change"))}</button></div>
    <div class="thread">
      ${cue}
      ${session.question ? `<article class="card"><div class="row"><p class="text grow">${esc(session.question)}</p><button class="icon-btn speak" type="button" data-act="speak-question" aria-label="${esc(t("play"))}">▶</button></div>${gloss ? `<details><summary>${esc(t("whatAsking"))}</summary><p>${esc(gloss)}</p></details>` : ""}</article>` : ""}
      ${(session.answers || []).map((item, index) => `<article class="bubble learner"><div class="said"><div class="row"><p class="text grow">${esc(item.text)}</p><button class="icon-btn speak" type="button" data-act="speak-answer" data-index="${index}" aria-label="${esc(t("play"))}">▶</button></div></div></article>`).join("")}
      ${review}
      ${state.notice ? `<p class="error">${esc(state.notice)}</p>` : ""}
    </div>
    ${session.phase === "ask" || session.phase === "part2_speak" || session.phase === "rounding" ? composerHtml() : ""}
    ${session.phase === "part2_prep" ? `<div class="composer"><p class="muted">${esc(t("prep"))}</p><textarea id="notes" placeholder="${esc(t("notes"))}">${esc(session.notes || "")}</textarea></div>` : ""}
    ${session.phase === "between" ? `<div class="composer"><button class="primary" type="button" data-act="ielts-next">${esc(t("next"))}</button></div>` : ""}
    ${session.phase === "done" ? `<div class="composer"><button class="primary" type="button" data-act="home">${esc(t("back"))}</button></div>` : ""}`;
}

function cueHtml(session) {
  if (session.part !== 2 || !session.cue) return "";
  if (session.kind === "mock") {
    return `<article class="card cue"><strong>${esc(session.cue.title)}</strong><ul>${session.cue.say.map((line) => `<li>${esc(line)}</li>`).join("")}</ul></article>`;
  }
  return `<article class="card cue"><strong>${esc(session.cue.title)}</strong><ul>${session.cue.say.map((line) => `<li>☐ ${esc(line)}</li>`).join("")}</ul></article>`;
}

function reviewHtml(review) {
  if (!review) return "";
  const criteria = (review.criteria || []).map((item) => {
    const band = item.status === "unscored" ? t("notAssessed") : `${t("practiceEstimate")} ${item.band}`;
    return `<p><strong>${esc(item.id)}</strong> — ${esc(band)}${item.evidence ? ` · ${esc(item.evidence)}` : ""}</p>`;
  }).join("");
  const bullets = (review.bullets || []).map((item) => `<li>${esc(item.id)}: ${item.covered ? esc(t("covered")) : esc(t("notYet"))}${item.quote ? ` “${esc(item.quote)}”` : ""}</li>`).join("");
  const length = review.length?.wpm ? `<p>about ${esc(review.length.words)} words in ${esc(Math.round(review.length.speech_ms / 1000))} seconds</p>` : "";
  return `<article class="card">
    <h2>${esc(t("review"))}</h2>
    <p>${esc(review.disclaimer?.estimate || t("disclaimer"))}</p>
    <p>${esc(review.disclaimer?.pronunciation || t("noBand"))}</p>
    ${criteria}
    ${bullets ? `<ul>${bullets}</ul>` : ""}
    ${length}
    <p><strong>${esc(t("trySaying"))}</strong></p>
    <p>${esc(review.practice_answer?.text || "")}</p>
    <p class="phonetic">${esc(review.practice_answer?.phonetic || "")}</p>
    <p>${esc(review.practice_answer?.why || "")}</p>
    <p class="small muted">${esc(t("weak"))}</p>
    <button class="ghost" type="button" data-act="speak-practice">${esc(t("play"))}</button>
  </article>`;
}

function sheet() {
  if (state.confirm) {
    return `<div class="backdrop" data-act="confirm-no"></div><section class="sheet"><p>${esc(state.confirm.text)}</p><div class="row"><button class="primary" type="button" data-act="confirm-yes">${esc(t("yes"))}</button><button class="ghost" type="button" data-act="confirm-no">${esc(t("cancel"))}</button></div></section>`;
  }
  if (state.sheet === "partners") return partnerSheet();
  if (state.sheet === "settings") return settingsSheet();
  return "";
}

function partnerSheet() {
  const selected = selectedPartnerId();
  const rows = state.catalogue.partners.map((item) => `
    <button class="partner-row" type="button" data-act="pick-partner" data-id="${esc(item.id)}" aria-pressed="${item.id === selected}">
      <img alt="" src="${esc(item.portrait)}">
      <span><strong>${esc(item.name)}</strong><br><span class="muted">${esc(item.city)} · 27 · ${esc(item.gender === "woman" ? "woman" : "man")}${roleLabel(item) ? ` · ${esc(roleLabel(item))}` : ""}</span><br><span class="small muted">${item.display === "mesh" ? esc(t("mesh")) : esc(t("illustrated"))}</span></span>
    </button>`).join("");
  return `<div class="backdrop" data-act="close-sheet"></div><section class="sheet"><div class="row"><h2 class="grow">${esc(t("change"))}</h2><button class="icon-btn" type="button" data-act="close-sheet">${esc(t("close"))}</button></div><p class="muted">${esc(t("womenMen"))}</p>${rows}</section>`;
}

function settingsSheet() {
  const s = state.settings;
  const hideScript = s.target === "en" && s.support === "en";
  const bands = [];
  for (let band = 5; band <= 8.01; band += 0.5) bands.push(band.toFixed(1));
  return `<div class="backdrop" data-act="close-sheet"></div><section class="sheet">
    <div class="row"><h2 class="grow">${esc(t("settings"))}</h2><button class="icon-btn" type="button" data-act="close-sheet">${esc(t("close"))}</button></div>
    ${selectField("support", t("support"), ["en", "cmn", "yue"], s.support)}
    ${selectField("target", t("target"), ["en", "cmn", "yue"], s.target)}
    ${selectField("level", t("level"), ["beginner", "intermediate", "advanced"], s.level, { beginner: t("begin"), intermediate: t("intermediate"), advanced: t("advanced") })}
    ${hideScript ? "" : selectField("script", t("script"), ["Hant", "Hans"], s.script)}
    ${selectField("accent", t("accent"), ["en-GB", "en-US"], s.accent)}
    ${selectField("pinyin_tone", t("pinyin"), ["mark", "number"], s.pinyin_tone, { mark: t("marks"), number: t("numbers") })}
    ${selectField("module", t("module"), ["academic", "general"], s.module)}
    ${selectField("target_band", t("band"), bands, Number(s.target_band).toFixed(1))}
    <label class="field"><span>${esc(t("exam"))}</span><input id="exam_date" type="date" value="${esc(s.exam_date || "")}"></label>
    <label class="field"><input id="autoplay" type="checkbox" ${s.autoplay ? "checked" : ""}> ${esc(t("autoplay"))}</label>
    <p class="small muted">${esc(t("privacy"))}</p>
    <p class="small muted">${esc(t("historyLoss"))}</p>
    <p class="small muted">${esc(t("adult"))}</p>
    <button class="primary" type="button" data-act="save-settings">${esc(t("save"))}</button>
  </section>`;
}

function selectField(name, label, values, current, names) {
  const options = values.map((value) => `<option value="${esc(value)}" ${String(value) === String(current) ? "selected" : ""}>${esc(names?.[value] || value)}</option>`).join("");
  return `<label class="field"><span>${esc(label)}</span><select id="set-${name}">${options}</select></label>`;
}

function historyView() {
  const rows = state.history.length ? state.history.map((item) => `<article class="card"><strong>${esc(item.task || item.track)}</strong><div class="muted">${esc(item.partner || "")} · ${esc(item.date || "")}</div><div>${esc(item.summary || "")}</div></article>`).join("") : `<p>${esc(t("emptyHistory"))}</p>`;
  return `<header class="top"><button class="icon-btn" type="button" data-act="home">${esc(t("back"))}</button><h1>${esc(t("history"))}</h1></header><main class="history">${rows}<p class="small muted">${esc(t("weak"))}</p></main>`;
}

function clockText() {
  const session = state.ielts;
  if (!session?.deadline) return "";
  const left = Math.max(0, session.deadline - Date.now());
  const total = Math.ceil(left / 1000);
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

app.addEventListener("click", (event) => {
  const el = eventElement(event);
  const mic = el?.closest?.("#mic");
  if (mic) {
    if (mic.disabled) return;
    if (micSuppressClick) {
      micSuppressClick = false;
      return;
    }
    toggleMic();
    return;
  }
  const button = el?.closest?.("[data-act]");
  if (!button) return;
  onAct(button.dataset.act, button.dataset);
});

app.addEventListener("submit", (event) => {
  if (event.target.id !== "composer") return;
  event.preventDefault();
  submitField();
});

app.addEventListener("input", (event) => {
  if (event.target.id === "field") composerDraft = event.target.value;
});

app.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target.id === "field" && !event.shiftKey) {
    event.preventDefault();
    submitField();
  }
  if ((event.key === " " || event.code === "Space") && event.target?.id === "mic") {
    event.preventDefault();
    if (event.repeat) return;
    toggleMic();
  }
});

app.addEventListener("scroll", (event) => {
  const target = event.target;
  if (!target?.classList?.contains("thread")) return;
  if (performance.now() < ignoreThreadScrollUntil) return;
  const nearBottom = target.scrollHeight - target.scrollTop - target.clientHeight <= 120;
  // Pause auto-scroll while the user is reading older messages; resume at the bottom.
  threadUserScrolled = !nearBottom;
}, true);

app.addEventListener("pointerdown", (event) => {
  const mic = eventElement(event)?.closest?.("#mic");
  if (!mic || mic.disabled) return;
  if (event.button != null && event.button !== 0) return;
  clearMicHold();
  micSuppressClick = false;
  micGestureId = event.pointerId;
  micDownAt = Date.now();
  micHoldTimer = window.setTimeout(() => {
    micHoldTimer = 0;
    micHolding = true;
    micSuppressClick = true;
    if (!listening && !micStartTimer) startMic();
  }, 450);
});

function finishMicPointer(event, cancelled) {
  if (micGestureId == null) return;
  if (event?.pointerId != null && event.pointerId !== micGestureId) return;
  if (cancelled) {
    micGestureId = null;
    return;
  }
  const held = micHolding;
  const downFor = Date.now() - micDownAt;
  clearMicHold();
  if (!held) return;
  micSuppressClick = true;
  if (downFor >= 800 && (listening || micStartTimer)) stopMic();
}

window.addEventListener("pointerup", (event) => finishMicPointer(event, false));
window.addEventListener("pointercancel", (event) => finishMicPointer(event, true));

app.addEventListener("contextmenu", (event) => {
  if (eventElement(event)?.closest?.("#mic")) event.preventDefault();
});

function onAct(act, data) {
  if (act === "or-status") { checkOpenRouter(); return; }
  if (act === "settings") { state.sheet = "settings"; render(); return; }
  if (act === "close-sheet") { state.sheet = null; render(); return; }
  if (act === "partners") { state.sheet = "partners"; render(); return; }
  if (act === "history") { state.screen = "history"; state.sheet = null; render(); return; }
  if (act === "home") { stopMic(); state.screen = "home"; state.sheet = null; state.ielts = null; render(); return; }
  if (act === "save-settings") { applySettings(); return; }
  if (act === "confirm-no") { state.confirm = null; render(); return; }
  if (act === "confirm-yes") { const pending = state.confirm; state.confirm = null; pending?.run(); return; }
  if (act === "pick-partner") { pickPartner(data.id); return; }
  if (act === "teacher-mode") { state.teacherMode = data.mode; saveTeacherMode(); render(); return; }
  if (act === "teacher") { openEnglishTeacher(); return; }
  if (act === "daily") { openDaily(state.catalogue.scenarios[0].id); return; }
  if (act === "scenario") { changeScenario(data.id); return; }
  if (act === "again") { openDaily(state.daily.scenario_id, true); return; }
  if (act === "drill") { startIelts(loadPlan().next ? "drill" : "diagnostic"); return; }
  if (act === "mock") { startIelts("mock"); return; }
  if (act === "speak") { speakBubble(Number(data.index)); return; }
  if (act === "speak-draft") { speakDraft(); return; }
  if (act === "speak-question") { speakExaminer(state.ielts?.question, "question"); return; }
  if (act === "speak-answer") {
    const text = state.ielts?.answers?.[Number(data.index)]?.text;
    if (text) speakText(text, "en", partner(), null, "encourage");
    return;
  }
  if (act === "speak-suggest") { speakSuggestion(); return; }
  if (act === "speak-practice") { speakPractice(); return; }
  if (act === "translate") {
    state.daily.bubbles[Number(data.index)].showTranslation = true;
    render();
    return;
  }
  if (act === "retry") { retryTurn(); return; }
  if (act === "ielts-next") { advanceAfterReview(); return; }
}

function applySettings() {
  const next = { ...state.settings };
  for (const key of ["support", "target", "level", "script", "accent", "pinyin_tone", "module", "target_band"]) {
    const node = document.querySelector(`#set-${key}`);
    if (node) next[key] = key === "target_band" ? Number(node.value) : node.value;
  }
  const exam = document.querySelector("#exam_date");
  const auto = document.querySelector("#autoplay");
  if (exam) next.exam_date = exam.value;
  if (auto) next.autoplay = auto.checked;
  const changed = ["target", "support", "script", "accent", "level"].some((key) => next[key] !== state.settings.target && key === "target" ? next.target !== state.settings.target : next[key] !== state.settings[key]);
  const resetKeys = ["target", "support", "level", "script", "accent"];
  const mustReset = resetKeys.some((key) => next[key] !== state.settings[key]) && learnerLines().length;
  const commit = () => {
    state.settings = next;
    saveSettings();
    state.sheet = null;
    if (mustReset && state.screen === "daily") openDaily(state.daily.scenario_id, true);
    else render();
  };
  if (mustReset) {
    state.sheet = null;
    state.confirm = { text: t("startNew"), run: commit };
    render();
    return;
  }
  commit();
  if (changed) state.notice = "";
}

function learnerLines() {
  return (state.daily?.bubbles || []).filter((bubble) => bubble.role === "learner" && bubble.text.trim());
}

function changeScenario(id) {
  if (!state.daily || id === state.daily.scenario_id) return;
  const run = () => openDaily(id, true);
  if (learnerLines().length) {
    state.confirm = { text: t("startNew"), run };
    render();
    return;
  }
  run();
}

function sceneHasLearnerLines(scene) {
  return (scene?.bubbles || []).some((bubble) => bubble.role === "learner" && String(bubble.text || "").trim());
}

function openEnglishTeacher() {
  const saved = state.screen === "daily" && state.daily ? state.daily : loadOpen();
  const same = saved && saved.scenario_id === "english-teacher";
  const busy = saved && !same && sceneHasLearnerLines(saved);
  const run = () => openDaily("english-teacher", !same, TEACHER_ID);
  if (busy) {
    state.sheet = null;
    state.confirm = { text: t("startNew"), run };
    render();
    return;
  }
  run();
}

function openCafeWaitress() {
  const saved = state.screen === "daily" && state.daily ? state.daily : loadOpen();
  const same = saved && saved.scenario_id === CAFE_SCENE;
  const busy = saved && !same && sceneHasLearnerLines(saved);
  const run = () => openDaily(CAFE_SCENE, !same, CAFE_ID);
  if (busy) {
    state.sheet = null;
    state.confirm = { text: t("startNew"), run };
    render();
    return;
  }
  run();
}

async function openDaily(scenarioId, force, partnerId) {
  const saved = !force && loadOpen();
  state.screen = "daily";
  state.sheet = null;
  state.notice = "";
  composerDraft = "";
  const retiredTeacher = scenarioId === "english-teacher" && (saved?.bubbles || []).some((bubble) => {
    const text = `${bubble.text || ""} ${bubble.translation || ""}`;
    return text.includes("I am Nora") || text.includes("我是 Nora") || text.includes("我係 Nora");
  });
  if (saved && saved.scenario_id === scenarioId && !retiredTeacher) {
    state.daily = saved;
    if (state.daily.partner_id === "nora") state.daily.partner_id = TEACHER_ID;
    if (partnerId) {
      state.daily.partner_id = partnerId;
      state.settings.partner = partnerId;
      saveSettings();
    } else if (scenarioId === "english-teacher" && !state.daily.partner_id) {
      state.daily.partner_id = TEACHER_ID;
    }
    saveOpen();
    render();
    scrollThread(true);
    return;
  }
  const assigned = partnerId || (scenarioId === "english-teacher" ? TEACHER_ID : null);
  if (assigned) {
    state.settings.partner = assigned;
    saveSettings();
  }
  state.daily = {
    session_id: uuid(),
    scenario_id: scenarioId,
    bubbles: [],
    fired: [],
    goal: "open",
    cap_reached: false,
    partner_id: assigned,
  };
  render();
  await postTurn([]);
}

function loadOpen() {
  try {
    return JSON.parse(localStorage.getItem("lingocoach.open.v1") || "null");
  } catch (err) {
    return null;
  }
}

function saveOpen() {
  if (!state.daily) return;
  localStorage.setItem("lingocoach.open.v1", JSON.stringify(state.daily));
}

async function submitField() {
  const field = document.querySelector("#field");
  const text = (field?.value || composerDraft || "").trim();
  if (!text || state.daily?.loading || state.ielts?.loading) return;
  stopMic();
  if (state.screen === "ielts") {
    clearDraft();
    await submitIelts(text);
    return;
  }
  // The user is sending a new message, so they want to see the reply.
  threadUserScrolled = false;
  const bubble = { role: "learner", text, pending: true };
  state.daily.bubbles.push(bubble);
  clearDraft();
  render();
  const history = state.daily.bubbles.filter((item) => item.role === "learner" || item.role === "character").slice(-12).map((item) => ({ role: item.role, text: item.text }));
  await postTurn(history);
}

async function postTurn(history) {
  state.daily.loading = true;
  const body = {
    session_id: state.daily.session_id,
    scenario_id: state.daily.scenario_id,
    partner_id: state.daily.partner_id || state.settings.partner,
    settings: {
      target: practiceTarget(),
      support: state.settings.support,
      level: state.settings.level,
      script: state.settings.script,
      accent: state.settings.accent,
      pinyin_tone: state.settings.pinyin_tone,
      partner: state.settings.partner,
      mode: state.teacherMode,
    },
    history,
    fired_signals: state.daily.fired || [],
  };
  state.lastBody = body;
  let response;
  try {
    response = await fetch("/api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Client-Id": clientId() },
      body: JSON.stringify(body),
    });
  } catch (err) {
    markLearnerError(t("network"));
    return;
  }
  if (response.status === 429) {
    markLearnerError(t("tooMany"));
    return;
  }
  if (!response.ok) {
    markLearnerError(response.status === 502 ? t("coachUnavailable") : t("retry"));
    return;
  }
  const data = await response.json();
  state.provider = data.meta?.provider || state.provider;
  const learner = [...state.daily.bubbles].reverse().find((item) => item.role === "learner");
  if (learner) {
    learner.pending = false;
    learner.error = "";
    learner.coaching = data.coaching;
  }
  if (data.character?.text) {
    state.daily.bubbles.push({
      role: "character",
      text: data.character.text,
      translation: data.character.translation,
      phonetic: data.character.phonetic,
      phonetic_system: data.character.phonetic_system,
      syllables: data.character.syllables,
      visemes: data.character.visemes,
      mood: data.character.mood,
      partner_id: data.partner_id || state.settings.partner,
    });
  }
  state.daily.fired = data.session?.fired_signals || [];
  state.daily.goal = data.session?.goal_status || "open";
  state.daily.cap_reached = Boolean(data.session?.cap_reached);
  state.daily.loading = false;
  saveOpen();
  if (state.daily.goal === "met" || state.daily.cap_reached) saveHistoryRow();
  render();
  const last = state.daily.bubbles[state.daily.bubbles.length - 1];
  if (last?.role === "character") {
    scrollThread(true);
    if (state.settings.autoplay) speakLine(last);
  }
}

function markLearnerError(message) {
  const learner = [...state.daily.bubbles].reverse().find((item) => item.role === "learner");
  if (learner) {
    learner.pending = false;
    learner.error = message;
  }
  state.daily.loading = false;
  state.notice = message;
  render();
}

async function retryTurn() {
  if (!state.lastBody) return;
  const learner = [...state.daily.bubbles].reverse().find((item) => item.role === "learner");
  if (learner) {
    learner.pending = true;
    learner.error = "";
  }
  render();
  await postTurn(state.lastBody.history);
}

function pickPartner(id) {
  const session = state.ielts;
  if (session && session.kind === "mock" && (session.phase === "part2_prep" || session.phase === "part2_speak")) return;
  if (listening) return;
  if (id === TEACHER_ID) {
    if (state.screen === "daily" && state.daily?.scenario_id === "english-teacher") {
      state.daily.partner_id = TEACHER_ID;
      saveOpen();
      state.sheet = null;
      const name = activePartner()?.name || id;
      render();
      const live = document.querySelector("#live");
      if (live) live.textContent = `${t("nowTalking")} ${name}`;
      return;
    }
    openEnglishTeacher();
    return;
  }
  if (id === CAFE_ID) {
    if (state.screen === "daily" && state.daily?.scenario_id === CAFE_SCENE) {
      state.settings.partner = CAFE_ID;
      state.daily.partner_id = CAFE_ID;
      saveSettings();
      saveOpen();
      state.sheet = null;
      render();
      const live = document.querySelector("#live");
      if (live) live.textContent = `${t("nowTalking")} ${activePartner()?.name || "Celine"}`;
      return;
    }
    openCafeWaitress();
    return;
  }
  state.settings.partner = id;
  saveSettings();
  if (state.screen === "daily" && state.daily) {
    state.daily.partner_id = id;
    saveOpen();
  }
  state.sheet = null;
  const name = (state.screen === "daily" ? activePartner() : partner())?.name || id;
  const live = document.querySelector("#live");
  if (live) live.textContent = `${t("nowTalking")} ${name}`;
  if (state.speaking) {
    const line = { ...state.speaking };
    render();
    speakText(line.text, line.lineLang, partner(), line.visemes, line.mood);
    return;
  }
  render();
}

function eventElement(event) {
  const node = event?.target;
  if (!node) return null;
  return node.nodeType === 1 ? node : node.parentElement;
}

function clearMicHold() {
  window.clearTimeout(micHoldTimer);
  micHoldTimer = 0;
  micHolding = false;
  micGestureId = null;
}

function toggleMic() {
  if (listening || micStartTimer) stopMic();
  else startMic();
}

function localhostHref() {
  const port = location.port || "8066";
  const path = location.pathname && location.pathname !== "/" ? location.pathname : "";
  return `http://127.0.0.1:${port}${path}${location.search || ""}`;
}

function recognitionContextOk() {
  const host = String(location.hostname || "").toLowerCase();
  if (host === "localhost" || host === "127.0.0.1") return true;
  return window.isSecureContext === true;
}

function micBlock() {
  if (!recognitionContextOk()) return "insecure";
  if (!(window.SpeechRecognition || window.webkitSpeechRecognition)) return "unsupported";
  if (state.micHidden) return "hidden";
  if (practiceTarget() === "yue" && state.cantoneseMicHidden) return "cantonese";
  return "";
}

function speechAvailable() {
  return micBlock() === "";
}

function statusHtml() {
  const block = micBlock();
  if (block === "insecure") {
    const url = localhostHref();
    return `<p id="status" class="banner error" role="status">${esc(t("micInsecure"))} <a class="inline" href="${esc(url)}">${esc(url)}</a></p>`;
  }
  const text = listening
    ? t("listening")
    : state.micMessage || (block === "unsupported" ? t("micUnsupported") : block === "cantonese" ? t("noCantoneseMic") : "");
  if (!text) return `<p id="status" class="banner" role="status" hidden></p>`;
  const error = !listening && (Boolean(state.micMessage) || block === "unsupported" || block === "cantonese");
  const liveClass = listening ? " listening" : "";
  return `<p id="status" class="banner${liveClass}${error ? " error" : ""}" role="status">${esc(text)}</p>`;
}

function showStatus(text, isError) {
  state.micMessage = text || "";
  announce(text || "");
  const node = document.querySelector("#status");
  if (!node) return;
  node.hidden = !text;
  node.className = isError ? "banner error" : "banner";
  node.textContent = text || "";
}

function clearDraft() {
  acceptMicText = false;
  composerDraft = "";
  const field = document.querySelector("#field");
  if (field) field.value = "";
}

function paintMic(live) {
  const mic = document.querySelector("#mic");
  if (!mic) return;
  if (mic.disabled) {
    mic.classList.remove("live");
    mic.textContent = "🎤";
    return;
  }
  mic.classList.toggle("live", Boolean(live));
  mic.setAttribute("aria-pressed", live ? "true" : "false");
  mic.setAttribute("aria-label", live ? `${t("listening")}. Stop` : t("placeholder"));
  mic.textContent = live ? t("listening") : "🎤";
}

function recognitionResults(ev) {
  const results = ev?.results;
  const viaHelper = collectTranscript(results);
  if (!results || typeof results.length !== "number") return viaHelper;
  let text = "";
  for (let i = 0; i < results.length; i += 1) {
    text += transcriptPiece(results, i);
  }
  return text.trim() || viaHelper;
}

function writeRecognition(text) {
  const heard = String(text || "").trim();
  if (!heard) return;
  micHeard = true;
  composerDraft = heard;
  const field = document.querySelector("#field");
  if (!field || field.value === heard) return;
  field.value = heard;
  try { field.setSelectionRange(heard.length, heard.length); } catch (err) { /* keep the text */ }
}

function micErrorText(code) {
  if (!recognitionContextOk()) return `${t("micInsecure")} ${localhostHref()}`;
  if (code === "not-allowed" || code === "service-not-allowed") return t("micBlocked");
  if (code === "network") return t("recNetwork");
  if (code === "audio-capture") return t("noMic");
  if (code === "no-speech") return t("noSpeech");
  if (code === "aborted") return t("micAborted");
  return t("micError").replace("{code}", code || "unknown");
}

function markListening() {
  listening = true;
  state.micMessage = "";
  if (face) {
    try {
      face.setMode("listen");
      face.setViseme("sil");
    } catch (err) { /* portrait */ }
  }
  if (state.ielts && !state.ielts.speechStarted && state.ielts.phase === "part2_speak") state.ielts.speechStarted = Date.now();
  state.micStarted = state.micStarted || Date.now();
  announce(t("listening"));
  const node = document.querySelector("#status");
  if (node) {
    node.hidden = false;
    node.className = "banner listening";
    node.textContent = t("listening");
  }
  paintMic(true);
}

function idleFace() {
  if (!face || state.speaking) return;
  try { face.setMode("idle"); } catch (err) { /* portrait */ }
}

function armRecognizer() {
  const Engine = window.SpeechRecognition || window.webkitSpeechRecognition;
  const session = new Engine();
  session.interimResults = true;
  session.continuous = false;
  session.maxAlternatives = 1;
  session.lang = recognitionLang();
  session.onstart = () => {
    micEngineStarted = true;
    if (micStopRequested) {
      try { session.stop(); } catch (err) { /* ending */ }
    }
  };
  session.onresult = (ev) => {
    if (!acceptMicText) return;
    try {
      const text = recognitionResults(ev);
      if (text) writeRecognition(text);
    } catch (err) {
      showStatus(micErrorText("result"), true);
    }
  };
  session.onerror = (ev) => {
    const code = ev?.error || "unknown";
    if (code === "language-not-supported" && practiceTarget() === "yue") {
      state.cantoneseMicHidden = true;
      listening = false;
      showStatus(t("noCantoneseMic"), true);
      paintMic(false);
      idleFace();
      return;
    }
    if (code === "aborted") {
      listening = false;
      paintMic(false);
      showStatus(t("micAborted"), false);
      idleFace();
      return;
    }
    if (code === "no-speech" && !micHeard) {
      const live = document.querySelector("#field");
      if (!live || live.value === draftBeforeMic || live.value === composerDraft) {
        composerDraft = draftBeforeMic;
        if (live) live.value = composerDraft;
      } else {
        composerDraft = live.value;
      }
    }
    listening = false;
    showStatus(micErrorText(code), code !== "no-speech");
    paintMic(false);
    idleFace();
  };
  session.onend = () => {
    listening = false;
    micEngineStarted = false;
    paintMic(false);
    const fieldNow = document.querySelector("#field");
    if (fieldNow && micHeard && composerDraft && fieldNow.value !== composerDraft) fieldNow.value = composerDraft;
    if (!state.micMessage) {
      const node = document.querySelector("#status");
      if (node && !node.querySelector("a")) {
        node.hidden = true;
        node.textContent = "";
        node.className = "banner";
      }
    }
    idleFace();
  };
  return session;
}

function startMic() {
  const block = micBlock();
  if (block === "insecure") {
    showStatus(`${t("micInsecure")} ${localhostHref()}`, true);
    return;
  }
  if (block === "unsupported" || block === "hidden") {
    showStatus(t("micUnsupported"), true);
    return;
  }
  if (block === "cantonese") {
    showStatus(t("noCantoneseMic"), true);
    return;
  }
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor || listening || micStartTimer) return;
  const field = document.querySelector("#field");
  draftBeforeMic = field ? field.value : composerDraft;
  composerDraft = draftBeforeMic;
  micHeard = false;
  acceptMicText = true;
  micEngineStarted = false;
  micStopRequested = false;
  state.micMessage = "";
  const synth = window.speechSynthesis;
  const wasSpeaking = Boolean(
    state.speaking || activeUtterance || speakTimer || (synth && (synth.speaking || synth.pending))
  );
  stopSpeaking();
  markListening();
  const begin = () => {
    micStartTimer = 0;
    if (micStopRequested) {
      listening = false;
      paintMic(false);
      idleFace();
      return;
    }
    const again = window.speechSynthesis;
    if (again) {
      try { again.cancel(); } catch (err) { /* idle */ }
    }
    try {
      if (recognizer) {
        try {
          recognizer.onstart = null;
          recognizer.onresult = null;
          recognizer.onerror = null;
          recognizer.onend = null;
        } catch (err) { /* replace */ }
      }
      recognizer = armRecognizer();
      recognizer.start();
    } catch (err) {
      listening = false;
      micEngineStarted = false;
      paintMic(false);
      showStatus(micErrorText(err?.name || "start"), true);
      idleFace();
    }
  };
  if (wasSpeaking) micStartTimer = window.setTimeout(begin, 250);
  else begin();
}

function stopMic() {
  window.clearTimeout(micStartTimer);
  micStartTimer = 0;
  const wasListening = listening || micEngineStarted;
  micStopRequested = true;
  listening = false;
  paintMic(false);
  if (wasListening && !state.micMessage) announce(t("stopped"));
  if (!recognizer || !micEngineStarted) return;
  try { recognizer.stop(); } catch (err) { /* already stopped */ }
}

function recognitionLang() {
  return recognitionLanguage(practiceTarget(), state.settings.accent);
}

function announce(text) {
  const live = document.querySelector("#live");
  if (live) live.textContent = text;
}

function refreshVoices() {
  voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
}
if (window.speechSynthesis) {
  window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
  refreshVoices();
  setTimeout(refreshVoices, 400);
}

function voiceCode(voice) {
  return String(voice?.lang || "").toLowerCase().replaceAll("_", "-");
}

function isCantoneseVoice(voice) {
  const code = voiceCode(voice);
  if (!code || code.startsWith("zh-cn") || code.startsWith("zh-tw") || code.startsWith("zh-hans")) return false;
  return code.startsWith("zh-hk") || code.startsWith("yue");
}

function isNamedFemaleVoice(name) {
  return /female|woman|samantha|victoria|karen|moira|fiona|serena|kate|libby|sonia|aria|jenny|tessa|zira|hazel|susan|allison|ava|emma|emily|joanna|salli|kimberly|kendra|nicole|natasha|veena|xiaoxiao|huihui|yaoyao|sinji|tingting|meijia/i.test(name || "");
}

function isNamedMaleVoice(name) {
  return /\bmale\b|daniel|alex|rishi|\btom\b|david|mark|james|george|fred|bruce|aaron|guy|matthew|justin|joey|brian|eric|oliver|thomas/i.test(name || "");
}

/** Prefer sweet, younger-sounding female names (Chloe / women) over generic or older voices. */
function youngSweetFemaleBonus(name) {
  const n = name || "";
  // Explicit young/sweet English female voices (Chrome, macOS, Edge, etc.)
  if (/google uk english female|uk english female|microsoft zira|zira|samantha|karen|victoria|tessa|fiona|aria|jenny|moira|serena|kate|libby|sonia|hazel|susan|allison|ava|emma|emily|joanna|salli|kimberly|kendra|nicole|natasha/i.test(n)) {
    return 3;
  }
  if (/female|woman/i.test(n)) return 2;
  if (isNamedFemaleVoice(n)) return 1;
  return 0;
}

function byGender(list, person) {
  const wantMale = person?.gender === "man";
  const score = (voice) => {
    const name = voice?.name || "";
    const isFemale = isNamedFemaleVoice(name);
    const isMale = !isFemale && isNamedMaleVoice(name);
    let base = 1;
    if (wantMale && isMale) base = 2;
    else if (!wantMale && isFemale) base = 2;
    else if (wantMale && isFemale) base = 0;
    else if (!wantMale && isMale) base = 0;
    if (!wantMale) base += youngSweetFemaleBonus(name);
    return base;
  };
  return [...list].sort((a, b) => score(b) - score(a) || String(a.name || "").localeCompare(String(b.name || "")));
}

function voiceFor(lineLang, who) {
  const person = who || partner() || {};
  const list = (window.speechSynthesis?.getVoices?.() || voices || []).filter((voice) => voice && voice.lang);
  if (list.length) voices = list;
  const lang = lineLang || "en";
  if (lang === "yue") {
    const pool = list.filter((voice) => isCantoneseVoice(voice));
    return pool.length ? byGender(pool, person)[0] : null;
  }
  if (lang === "cmn") {
    const pool = list.filter((voice) => {
      const code = voiceCode(voice);
      return code.startsWith("zh-cn") || code.startsWith("cmn");
    });
    if (pool.length) return byGender(pool, person)[0];
    return list.find((voice) => voice.default) || list[0] || null;
  }
  const english = list.filter((voice) => {
    const code = voiceCode(voice);
    return code === "en" || code.startsWith("en-");
  });
  // Chloe is a London teacher: prefer a sweet en-GB female voice when one exists.
  const preferGb = person?.id === "chloe" || state.settings.accent !== "en-US";
  const prefer = preferGb ? "en-gb" : "en-us";
  const exact = english.filter((voice) => voiceCode(voice).startsWith(prefer));
  if (exact.length) {
    const ranked = byGender(exact, person);
    if (person?.id === "chloe") {
      const sweetGb = ranked.find((voice) => youngSweetFemaleBonus(voice.name) > 0);
      if (sweetGb) return sweetGb;
    } else {
      return ranked[0];
    }
  }
  if (english.length) {
    const ranked = byGender(english, person);
    if (person?.id === "chloe" || person?.gender === "woman") {
      const sweet = ranked.find((voice) => youngSweetFemaleBonus(voice.name) > 0);
      if (sweet) return sweet;
    }
    return ranked[0];
  }
  return list.find((voice) => voice.default) || list[0] || null;
}

function utterancePitch(person) {
  if (person?.gender === "man") return 1;
  // Slightly brighter for women / Chloe without going cartoonish.
  return person?.id === "chloe" ? 1.12 : 1.08;
}

function utteranceLang(lineLang, voice) {
  if (lineLang === "yue") return isCantoneseVoice(voice) ? voice.lang : "zh-HK";
  if (lineLang === "cmn") return voiceCode(voice).startsWith("zh-cn") || voiceCode(voice).startsWith("cmn") ? voice.lang : "zh-CN";
  if (voice && (voiceCode(voice) === "en" || voiceCode(voice).startsWith("en-"))) return voice.lang;
  return state.settings.accent === "en-US" ? "en-US" : "en-GB";
}

function shapesFor(text, lineLang, visemes) {
  try {
    if (Array.isArray(visemes) && visemes.length) return visemes;
    if ((lineLang || "en") === "en") return englishVisemes(String(text || ""));
    return pinyinVisemes(String(text || ""));
  } catch (err) {
    return ["sil"];
  }
}

function speakLine(bubble) {
  const who = (state.catalogue.partners || []).find((item) => item.id === bubble.partner_id) || activePartner();
  const lang = practiceTarget();
  speakText(bubble.text, lang, who, bubble.visemes, bubble.mood || "happy");
}

function speakBubble(index) {
  const bubble = state.daily?.bubbles?.[index];
  if (bubble) speakLine(bubble);
}

function speakDraft() {
  const field = document.querySelector("#field");
  const text = (field?.value || composerDraft || "").trim();
  if (!text) return;
  const lang = practiceTarget();
  speakText(text, lang, activePartner(), null, "encourage");
}

function speakSuggestion() {
  const learner = [...(state.daily?.bubbles || [])].reverse().find((item) => item.coaching?.suggested_reply);
  if (!learner) return;
  const lang = practiceTarget();
  speakText(learner.coaching.suggested_reply, lang, activePartner(), learner.coaching.suggested_reply_visemes, "encourage");
}

function speakPractice() {
  const text = state.ielts?.review?.practice_answer?.text;
  if (!text) return;
  speakText(text, "en", partner(), state.ielts.review.practice_answer.visemes, "encourage");
}

function finishMouth() {
  window.clearInterval(mouthTimer);
  state.speaking = null;
  if (!face) return;
  try {
    face.setViseme("sil");
    face.setMode(listening ? "listen" : "idle");
  } catch (err) {
    /* portrait must not block the page */
  }
}

function stopSpeaking() {
  speakToken += 1;
  window.clearTimeout(speakTimer);
  window.clearInterval(mouthTimer);
  activeUtterance = null;
  const synth = window.speechSynthesis;
  if (synth) {
    try { synth.cancel(); } catch (err) { /* already idle */ }
    try { if (synth.paused) synth.resume(); } catch (err) { /* Chrome leaves the engine paused */ }
  }
  finishMouth();
}

const VOWEL_HOLD = { aa: 2.6, E: 2.15, I: 1.75, O: 2.45, U: 2.05 };

function visemeHold(name) {
  if (VOWEL_HOLD[name]) return VOWEL_HOLD[name];
  if (name === "sil") return 1.2;
  if (name === "PP") return 0.8;
  return 0.95;
}

function runMouth(shapes, mood, token, lineLang, rate) {
  const sequence = shapes.length ? shapes : ["sil"];
  const unit = (lineLang === "en" ? 74 : 102) / Math.max(0.72, rate || 1);
  const marks = [];
  let acc = 0;
  for (const name of sequence) {
    marks.push(acc);
    acc += visemeHold(name) * unit;
  }
  const total = Math.max(acc, 280);
  const endAt = performance.now() + total + 160;
  let clockOffset = 0;
  let clockAt = performance.now();
  const apply = () => {
    if (token !== speakToken) {
      window.clearInterval(mouthTimer);
      return;
    }
    if (!face) return;
    const elapsed = clockOffset + (performance.now() - clockAt);
    let index = 0;
    while (index < marks.length - 1 && elapsed >= marks[index + 1]) index += 1;
    const name = sequence[index] || "sil";
    const upcoming = sequence[Math.min(sequence.length - 1, index + 1)] || name;
    const end = index < marks.length - 1 ? marks[index + 1] : total;
    const span = Math.max(1, end - marks[index]);
    const local = Math.max(0, Math.min(1, (elapsed - marks[index]) / span));
    const anticipate = local > 0.72 ? ((local - 0.72) / 0.28) * 0.4 : 0;
    try { face.setViseme(name, upcoming, anticipate); } catch (err) { /* audio still plays */ }
  };
  if (face) {
    try {
      face.setMode("speak", mood || "happy");
      face.setViseme(sequence[0] || "sil", sequence[1] || sequence[0] || "sil", 0);
    } catch (err) {
      /* keep going to speechSynthesis */
    }
  }
  mouthTimer = window.setInterval(apply, 32);
  return {
    total,
    endAt,
    sync(charIndex, length) {
      const frac = length > 0 ? Math.max(0, Math.min(0.96, charIndex / length)) : 0;
      clockOffset = frac * total;
      clockAt = performance.now();
      apply();
    },
  };
}

function speakText(text, lineLang, who, visemes, mood) {
  const spoken = String(text || "").trim();
  if (!spoken) return;
  const token = ++speakToken;
  window.clearTimeout(speakTimer);
  window.clearInterval(mouthTimer);
  const synth = window.speechSynthesis;
  if (synth) {
    try { synth.cancel(); } catch (err) { /* idle */ }
    try { if (synth.paused) synth.resume(); } catch (err) { /* Chrome pause bug */ }
  }
  const person = who || partner() || { id: state.settings.partner, gender: "woman" };
  const lang = lineLang || "en";
  const shapes = shapesFor(spoken, lang, visemes);
  const rate = sessionRate || (state.settings.level === "beginner" ? 0.85 : 1);
  state.speaking = { text: spoken, lineLang: lang, partner_id: person.id, visemes: shapes, mood: mood || "happy" };
  const mouth = runMouth(shapes, mood, token, lang, rate);
  let said = false;
  const finishWhenReady = () => {
    if (token !== speakToken) return;
    const left = mouth.endAt - performance.now();
    if (left <= 0) finishMouth();
    else window.setTimeout(finishWhenReady, left);
  };
  const say = () => {
    if (token !== speakToken || said) return;
    said = true;
    const synthNow = window.speechSynthesis;
    if (synthNow) {
      try { voices = synthNow.getVoices() || voices; } catch (err) { /* keep the last list */ }
    }
    const voice = voiceFor(lang, person);
    if (lang === "yue" && !isCantoneseVoice(voice)) {
      const message = t("noCantoneseVoice");
      state.notice = message;
      showStatus(message, true);
      document.querySelectorAll("button.speak").forEach((button) => { button.title = message; });
      finishWhenReady();
      return;
    }
    if (!synthNow) {
      announce(t("noSynth"));
      finishWhenReady();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(spoken);
    activeUtterance = utterance;
    utterance.lang = utteranceLang(lang, voice);
    if (voice && (lang !== "yue" || isCantoneseVoice(voice))) {
      try { utterance.voice = voice; } catch (err) { /* lang is already set; still speak */ }
    }
    utterance.rate = rate;
    utterance.pitch = utterancePitch(person);
    utterance.onend = finishWhenReady;
    utterance.onerror = finishWhenReady;
    utterance.onboundary = (event) => {
      if (token !== speakToken) return;
      if (event.name && event.name !== "word" && event.name !== "sentence") return;
      const idx = event.charIndex || 0;
      if (idx <= 0) return;
      mouth.sync(idx, spoken.length);
    };
    try {
      if (synthNow.paused) synthNow.resume();
      synthNow.speak(utterance);
      if (synthNow.paused) synthNow.resume();
    } catch (err) {
      announce(t("noSynth"));
      finishWhenReady();
    }
  };
  const listed = synth?.getVoices?.() || [];
  const delay = listed.length ? 60 : 300;
  speakTimer = window.setTimeout(say, delay);
  if (synth && !listed.length) {
    try {
      synth.addEventListener("voiceschanged", () => {
        if (token !== speakToken || said) return;
        if (!(synth.getVoices() || []).length) return;
        window.clearTimeout(speakTimer);
        speakTimer = window.setTimeout(say, 60);
      }, { once: true });
    } catch (err) {
      /* the timeout still speaks */
    }
  }
}

async function mountFace() {
  const token = ++mountToken;
  const canvas = document.querySelector("#face");
  if (!canvas) {
    face = null;
    return;
  }
  const who = state.screen === "daily" ? activePartner() : partner();
  if (!who) return;
  if (who.mesh && who.mesh_url) {
    try {
      const portrait = new Portrait(canvas);
      portrait.ready = false;
      face = portrait;
      await portrait.load(who.portrait, who.mesh_url);
      if (token !== mountToken) return;
      portrait.ready = true;
      if (state.speaking) portrait.setMode("speak", state.speaking.mood || "happy");
      else portrait.setMode(listening ? "listen" : "idle");
      return;
    } catch (err) {
      /* fall through to the illustrated card */
    }
  }
  if (token !== mountToken) return;
  const illustrated = new IllustratedPortrait(canvas, who);
  illustrated.ready = true;
  face = illustrated;
  if (state.speaking) illustrated.setMode("speak", state.speaking.mood || "happy");
  else illustrated.setMode(listening ? "listen" : "idle");
}

function loop(now) {
  const dt = Math.min(0.05, (now - lastFrame) / 1000);
  lastFrame = now;
  if (face && face.ready !== false) {
    try {
      face.resize();
      face.frame(now, dt);
    } catch (err) {
      /* one bad frame must not stop the portrait loop */
    }
  }
  const clock = document.querySelector("#clock");
  if (clock && state.ielts) clock.textContent = clockText();
  tickIelts();
  requestAnimationFrame(loop);
}

function loadPlan() {
  const rows = JSON.parse(localStorage.getItem("lingocoach.ielts.v1") || "[]");
  const last = rows[rows.length - 1];
  let drillsSince = 0;
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    if (rows[i].kind === "mock" || rows[i].kind === "diagnostic") break;
    drillsSince += 1;
  }
  return { next: last?.next_drill || null, drillsSince, label: last?.next_drill ? `${last.next_drill.focus}` : "" };
}

function examSoon() {
  if (!state.settings.exam_date) return false;
  const when = new Date(state.settings.exam_date);
  const days = (when.getTime() - Date.now()) / 86400000;
  return days >= 0 && days <= 14;
}

function startIelts(kind) {
  const plan = loadPlan();
  const bank = state.catalogue.ielts;
  let prompt;
  let part = 1;
  if (kind === "mock") {
    prompt = promptById("food-at-home");
    part = 1;
  } else if (kind === "drill" && plan.next) {
    prompt = promptById(plan.next.prompt_id) || promptById("food-at-home");
    part = plan.next.part || prompt.part;
    kind = "drill";
  } else {
    kind = "diagnostic";
    prompt = promptById("food-at-home");
    part = 1;
  }
  state.screen = "ielts";
  state.sheet = null;
  state.notice = "";
  state.ielts = {
    kind,
    phase: "ask",
    part,
    prompt,
    frameIds: kind === "mock" ? bank.filter((item) => item.part === 1).slice(0, 3).map((item) => item.id) : [prompt.id],
    frameIndex: 0,
    qIndex: 0,
    question: "",
    gloss: "",
    cue: prompt.cue || null,
    answers: [],
    review: null,
    reviews: [],
    continued: false,
    speechStarted: null,
    deadline: null,
    notes: "",
    take: "",
    part3Index: 0,
    loading: false,
    hardStopped: false,
  };
  if (part === 2) beginPart2();
  else askCurrent();
  render();
  speakExaminer(state.ielts.question, state.ielts.kind === "mock" ? "examiner" : "question");
}

function askCurrent() {
  const session = state.ielts;
  const prompt = session.part === 3 ? promptById("skill-you-taught") : promptById(session.frameIds[session.frameIndex]) || session.prompt;
  session.prompt = prompt;
  let question = "";
  if (session.part === 1) question = prompt.questions[session.qIndex];
  else if (session.part === 3) question = prompt.part3[session.part3Index];
  else question = prompt.rounding_off?.[0] || "";
  session.question = question;
  session.gloss = session.kind === "mock" ? "" : (prompt.gloss?.[state.settings.support] || prompt.gloss?.en || "");
  session.cue = session.part === 2 ? prompt.cue : null;
  if (session.kind === "mock" && session.part === 1 && !session.deadline) session.deadline = Date.now() + 5 * 60 * 1000;
  if (session.kind === "mock" && session.part === 3 && !session.deadline) session.deadline = Date.now() + 5 * 60 * 1000;
}

function beginPart2() {
  const session = state.ielts;
  const prompt = promptById(session.kind === "diagnostic" || session.kind === "mock" ? "skill-you-taught" : session.prompt.id);
  session.part = 2;
  session.prompt = prompt;
  session.phase = "part2_prep";
  session.cue = prompt.cue;
  session.question = "";
  session.gloss = session.kind === "mock" ? "" : (prompt.gloss?.[state.settings.support] || "");
  session.deadline = Date.now() + 60 * 1000;
  session.continued = false;
  session.speechStarted = null;
  session.take = "";
  session.hardStopped = false;
}

async function submitIelts(text) {
  const session = state.ielts;
  if (session.phase === "part2_prep") return;
  stopMic();
  clearDraft();
  if (session.phase === "part2_speak") {
    const speechMs = Date.now() - (session.speechStarted || Date.now());
    const hard = session.hardStopped;
    session.hardStopped = false;
    if (!hard && speechMs < 60000 && !session.continued) {
      session.continued = true;
      session.take = `${session.take} ${text}`.trim();
      session.question = "Can you tell me anything else?";
      clearDraft();
      render();
      speakExaminer(session.question, "examiner");
      return;
    }
    session.take = `${session.take} ${text}`.trim();
    session.answers.push({ part: 2, prompt_id: session.prompt.id, text: session.take, speech_ms: speechMs });
    session.phase = "rounding";
    session.question = session.prompt.rounding_off[0];
    session.deadline = null;
    render();
    speakExaminer(session.question, session.kind === "mock" ? "examiner" : "question");
    return;
  }
  if (session.phase === "rounding") {
    session.answers.push({ part: 2, prompt_id: session.prompt.id, text, speech_ms: null, rounding: true });
    if (session.kind === "mock") {
      session.part = 3;
      session.part3Index = 0;
      session.phase = "ask";
      session.deadline = Date.now() + 5 * 60 * 1000;
      askCurrent();
      render();
      speakExaminer(session.question, "examiner");
      return;
    }
    await reviewLatest(2, session.prompt.id, session.take);
    return;
  }
  const speechMs = state.micStarted ? Date.now() - state.micStarted : null;
  state.micStarted = null;
  session.answers.push({ part: session.part, prompt_id: session.prompt.id, text, speech_ms: speechMs });
  if (session.kind === "mock") {
    nextMockQuestion();
    return;
  }
  await reviewLatest(session.part, session.prompt.id, text, speechMs);
}

function nextMockQuestion() {
  const session = state.ielts;
  if (session.part === 1) {
    const prompt = promptById(session.frameIds[session.frameIndex]);
    if (session.qIndex + 1 < prompt.questions.length) session.qIndex += 1;
    else if (session.frameIndex + 1 < session.frameIds.length) {
      session.frameIndex += 1;
      session.qIndex = 0;
    } else {
      beginPart2();
      render();
      return;
    }
    askCurrent();
    render();
    speakExaminer(session.question, "examiner");
    return;
  }
  if (session.part === 3) {
    const prompt = promptById("skill-you-taught");
    if (session.part3Index + 1 < prompt.part3.length) {
      session.part3Index += 1;
      askCurrent();
      render();
      speakExaminer(session.question, "examiner");
      return;
    }
    finishMock();
  }
}

async function reviewLatest(part, promptId, text, speechMs) {
  const session = state.ielts;
  session.loading = true;
  session.phase = "review";
  render();
  const response = await fetch("/api/ielts/review", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Client-Id": clientId() },
    body: JSON.stringify({
      session_id: uuid(),
      kind: session.kind === "mock" ? "mock_part" : session.kind === "diagnostic" ? "diagnostic" : "drill",
      part,
      prompt_id: promptId,
      target_band: state.settings.target_band,
      support: state.settings.support,
      script: state.settings.script,
      accent: state.settings.accent,
      speech_ms: speechMs ?? null,
      notes: session.notes || null,
      learner_text: text,
    }),
  });
  if (!response.ok) {
    state.notice = t("retry");
    session.loading = false;
    session.phase = "between";
    render();
    return;
  }
  const review = await response.json();
  session.review = review;
  session.reviews.push(review);
  session.loading = false;
  session.phase = session.kind === "mock" ? "done" : "between";
  rememberReview(review, part);
  if (session.kind !== "mock") render();
  else render();
}

function advanceAfterReview() {
  const session = state.ielts;
  session.review = null;
  if (session.part === 1) {
    const prompt = session.prompt;
    if (session.qIndex + 1 < (prompt.questions || []).length) {
      session.qIndex += 1;
      session.phase = "ask";
      askCurrent();
      render();
      speakExaminer(session.question, "question");
      return;
    }
    if (session.kind === "diagnostic") {
      beginPart2();
      render();
      return;
    }
    session.phase = "done";
    render();
    return;
  }
  if (session.part === 2 && session.kind === "diagnostic") {
    session.part = 3;
    session.part3Index = 0;
    session.phase = "ask";
    session.prompt = promptById("skill-you-taught");
    askCurrent();
    render();
    speakExaminer(session.question, "question");
    return;
  }
  if (session.part === 3 && session.kind === "diagnostic" && session.part3Index < 1) {
    session.part3Index += 1;
    session.phase = "ask";
    askCurrent();
    render();
    speakExaminer(session.question, "question");
    return;
  }
  session.phase = "done";
  render();
}

async function finishMock() {
  const session = state.ielts;
  session.phase = "review";
  session.kind = "mock";
  const groups = [1, 2, 3].map((part) => {
    const rows = session.answers.filter((item) => item.part === part && !item.rounding);
    return { part, text: rows.map((item) => item.text).join("\n\n"), prompt: part === 1 ? "food-at-home" : "skill-you-taught" };
  });
  for (const group of groups) {
    if (!group.text.trim()) continue;
    const response = await fetch("/api/ielts/review", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Client-Id": clientId() },
      body: JSON.stringify({
        session_id: uuid(),
        kind: "mock_part",
        part: group.part,
        prompt_id: group.prompt,
        target_band: state.settings.target_band,
        support: state.settings.support,
        script: state.settings.script,
        accent: state.settings.accent,
        speech_ms: null,
        learner_text: group.text,
      }),
    });
    if (response.ok) {
      const review = await response.json();
      session.reviews.push(review);
      session.review = review;
      rememberReview(review, group.part, "mock");
    }
  }
  session.phase = "done";
  render();
}

function rememberReview(review, part, kind) {
  const rows = JSON.parse(localStorage.getItem("lingocoach.ielts.v1") || "[]");
  rows.push({
    at: new Date().toISOString(),
    kind: kind || state.ielts.kind,
    part,
    next_drill: review.next_drill,
    bands: Object.fromEntries((review.criteria || []).map((item) => [item.id, item.band])),
  });
  localStorage.setItem("lingocoach.ielts.v1", JSON.stringify(rows.slice(-40)));
  saveHistoryRow(review);
}

function tickIelts() {
  const session = state.ielts;
  if (!session?.deadline || session.hardStopped) return;
  if (Date.now() < session.deadline) return;
  if (session.phase === "part2_prep") {
    session.phase = "part2_speak";
    session.deadline = Date.now() + 120 * 1000;
    session.speechStarted = Date.now();
    const notes = document.querySelector("#notes");
    if (notes) session.notes = notes.value;
    render();
    if (speechAvailable()) {
      const mic = document.querySelector("#mic");
      if (mic) startMic({ preventDefault() {} });
    }
    return;
  }
  if (session.phase === "part2_speak") {
    session.hardStopped = true;
    const field = document.querySelector("#field");
    const text = (field?.value || composerDraft || "").trim();
    session.deadline = null;
    submitIelts(text || session.take || "...");
    return;
  }
  if (session.kind === "mock" && (session.part === 1 || session.part === 3)) {
    session.deadline = null;
    if (session.part === 1) beginPart2();
    else finishMock();
    render();
  }
}

function speakExaminer(text, mood) {
  if (!text) return;
  speakText(text, "en", partner(), null, mood);
}

async function saveHistoryRow(review) {
  const row = {
    session_id: state.daily?.session_id || uuid(),
    track: state.screen === "ielts" ? "ielts" : "daily",
    partner: partner()?.name,
    task: state.screen === "ielts" ? state.ielts?.prompt?.id : scenario()?.title?.en,
    date: new Date().toISOString(),
    summary: state.screen === "ielts" ? (review ? "criteria assessed, pronunciation not assessed" : "") : (state.daily?.goal || ""),
    bubbles: state.daily?.bubbles || [],
  };
  state.history = [row, ...state.history].slice(0, 50);
  try {
    const db = await openDb();
    const tx = db.transaction("sessions", "readwrite");
    tx.objectStore("sessions").put(row);
    const all = await reqAsPromise(tx.objectStore("sessions").getAll());
    if (all.length > 50) {
      all.sort((a, b) => String(a.date).localeCompare(String(b.date)));
      for (const old of all.slice(0, all.length - 50)) tx.objectStore("sessions").delete(old.session_id);
    }
  } catch (err) {
    /* history still sits in memory for this visit */
  }
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("lingocoach", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("sessions", { keyPath: "session_id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function reqAsPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function openRouterReason(reason) {
  if (reason === "no_key") return t("orNoKey");
  if (reason === "auth") return t("orRejected");
  if (reason === "unreachable") return t("orUnreachable");
  return t("orUnreachable");
}

function openRouterStatusText() {
  const llm = state.llm || { phase: "checking" };
  if (llm.phase !== "done") return t("orChecking");
  if (llm.connected) return t("orConnected");
  return openRouterReason(llm.reason);
}

function openRouterBar() {
  const llm = state.llm || { phase: "checking", connected: false, reason: "" };
  const checking = llm.phase !== "done";
  const ok = !checking && llm.connected;
  const cls = checking ? "wait" : ok ? "ok" : "bad";
  const reason = checking ? "checking" : ok ? "ok" : (llm.reason === "no_key" || llm.reason === "auth" || llm.reason === "unreachable" ? llm.reason : "unreachable");
  return `<footer class="llm-status" role="status" aria-live="polite" data-connected="${checking ? "pending" : ok ? "true" : "false"}" data-reason="${esc(reason)}">
    <p class="llm-copy"><span class="llm-label">${esc(t("orCheck"))}</span> <span class="llm-result ${cls}">${esc(openRouterStatusText())}</span></p>
    <button class="ghost" type="button" data-act="or-status">${esc(t("orRecheck"))}</button>
  </footer>`;
}

function rememberFields() {
  const field = document.querySelector("#field");
  if (field) composerDraft = field.value;
  const notes = document.querySelector("#notes");
  if (notes && state.ielts) state.ielts.notes = notes.value;
}

function paintOpenRouterBar() {
  const footer = document.querySelector("footer.llm-status");
  const copy = footer?.querySelector(".llm-result");
  if (!footer || !copy) {
    rememberFields();
    render();
    return;
  }
  const llm = state.llm || { phase: "checking", connected: false, reason: "" };
  const checking = llm.phase !== "done";
  const ok = !checking && llm.connected;
  copy.className = `llm-result ${checking ? "wait" : ok ? "ok" : "bad"}`;
  copy.textContent = openRouterStatusText();
  footer.dataset.connected = checking ? "pending" : ok ? "true" : "false";
  footer.dataset.reason = checking ? "checking" : ok ? "ok" : (llm.reason === "no_key" || llm.reason === "auth" || llm.reason === "unreachable" ? llm.reason : "unreachable");
}

async function checkOpenRouter() {
  const token = ++llmToken;
  rememberFields();
  state.llm = { phase: "checking", connected: false, reason: "" };
  paintOpenRouterBar();
  let next = { phase: "done", connected: false, reason: "unreachable" };
  try {
    const response = await fetch("/api/openrouter/status");
    const data = await response.json();
    if (data && data.connected === true) next = { phase: "done", connected: true, reason: "" };
    else if (data && (data.reason === "no_key" || data.reason === "auth" || data.reason === "unreachable")) {
      next = { phase: "done", connected: false, reason: data.reason };
    }
  } catch (err) {
    next = { phase: "done", connected: false, reason: "unreachable" };
  }
  if (token !== llmToken) return;
  state.llm = next;
  paintOpenRouterBar();
}

async function boot() {
  const response = await fetch("/api/catalogue");
  state.catalogue = await response.json();
  state.provider = state.catalogue.key_loaded ? "openrouter" : "fixture";
  try {
    const db = await openDb();
    state.history = await reqAsPromise(db.transaction("sessions").objectStore("sessions").getAll());
    state.history.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  } catch (err) {
    state.history = [];
  }
  const open = loadOpen();
  if (open?.bubbles?.length) {
    state.daily = open;
    state.screen = "daily";
  }
  render();
  if (state.screen === "daily") scrollThread(true);
  requestAnimationFrame(loop);
  checkOpenRouter();
}

boot();
