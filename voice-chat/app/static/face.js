// Facial motion for a frontal portrait. Landmark indices follow the MediaPipe
// face mesh (478 points). Anchor points after faceCount stay put, so the
// background does not swim when the mouth and head move.

const BROW_L = [70, 63, 105, 66, 107];
const BROW_R = [336, 296, 334, 293, 300];
const CHEEK_L = [50, 101, 205, 187];
const CHEEK_R = [280, 330, 425, 411];
const LID_UPPER_L = [160, 159, 158, 157, 173];
const LID_LOWER_L = [144, 145, 153, 154, 155];
const LID_UPPER_R = [387, 386, 385, 384, 398];
const LID_LOWER_R = [373, 374, 380, 381, 390];
const IRIS_L = [468, 469, 470, 471, 472];
const IRIS_R = [473, 474, 475, 476, 477];

const INNER_LIP = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95];
const LOWER_INNER = new Set([324, 318, 402, 317, 14, 87, 178, 88, 95]);
const LOWER_OUTER = new Set([146, 91, 181, 84, 17, 314, 405, 321, 375]);
const UPPER_LIP = new Set([191, 80, 81, 82, 13, 312, 311, 310, 415, 185, 40, 39, 37, 0, 267, 269, 270, 409, 61, 291, 78, 308]);
const LIP_INDICES = new Set([...INNER_LIP, ...LOWER_INNER, ...LOWER_OUTER, ...UPPER_LIP]);
function isLip(index) { return LIP_INDICES.has(index); }

const SHAPES = {
  sil: { open: 0.02, round: 0, wide: 0, jaw: 0, press: 0 },
  aa: { open: 0.74, round: 0.04, wide: 0.06, jaw: 0.55, press: 0 },
  E: { open: 0.46, round: 0, wide: 0.34, jaw: 0.24, press: 0 },
  I: { open: 0.22, round: 0, wide: 0.4, jaw: 0.08, press: 0 },
  O: { open: 0.58, round: 0.75, wide: 0, jaw: 0.34, press: 0 },
  U: { open: 0.34, round: 0.88, wide: 0, jaw: 0.16, press: 0 },
  PP: { open: 0, round: 0.02, wide: 0, jaw: 0, press: 1 },
  FF: { open: 0.2, round: 0, wide: 0.1, jaw: 0.08, press: 0.2 },
  TH: { open: 0.28, round: 0, wide: 0.1, jaw: 0.14, press: 0 },
  DD: { open: 0.26, round: 0, wide: 0.04, jaw: 0.16, press: 0 },
  kk: { open: 0.32, round: 0.1, wide: 0, jaw: 0.28, press: 0 },
  CH: { open: 0.24, round: 0.32, wide: 0, jaw: 0.12, press: 0 },
  SS: { open: 0.16, round: 0, wide: 0.16, jaw: 0.06, press: 0 },
  nn: { open: 0.14, round: 0, wide: 0.02, jaw: 0.08, press: 0 },
  RR: { open: 0.24, round: 0.3, wide: 0, jaw: 0.12, press: 0 },
};

export const MOODS = {
  neutral: { smile: 0.08, brow: 0 },
  happy: { smile: 0.7, brow: 0.16 },
  question: { smile: 0.14, brow: 0.9 },
  encourage: { smile: 0.82, brow: 0.2 },
  listen: { smile: 0.34, brow: 0.06 },
  examiner: { smile: 0.12, brow: 0.05 },
};

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function smoothstep(t) {
  const x = Math.max(0, Math.min(1, t));
  return x * x * (3 - 2 * x);
}

const MOUTH_KEYS = { open: 1, round: 1, wide: 1, jaw: 1, press: 1 };

function mouthLimits(rest, faceCount, triangles) {
  const mw = Math.hypot(rest[61][0] - rest[291][0], rest[61][1] - rest[291][1]) || 0.14;
  const lipTop = rest[0][1];
  const nose = Math.min(rest[4][1], rest[1][1], rest[2][1]);
  const noseSpan = Math.max(0.03, lipTop - nose);
  const chin = rest[152][1];
  const jaw = new Set();
  for (let i = 0; i < faceCount; i++) if (rest[i][1] > chin - 0.03) jaw.add(i);
  let clearance = 0.16;
  for (const tri of triangles || []) {
    let touches = false;
    const anchors = [];
    for (const index of tri) {
      if (jaw.has(index)) touches = true;
      else if (index >= faceCount) anchors.push(index);
    }
    if (!touches) continue;
    for (const index of anchors) {
      const gap = rest[index][1] - chin;
      if (gap > 0.01) clearance = Math.min(clearance, gap);
    }
  }
  return {
    mw,
    lipTop,
    nose,
    chin,
    clearance,
    up: Math.min(mw * 0.22, noseSpan * 0.48),
    down: Math.min(mw * 0.34, Math.max(0.014, clearance * 0.34)),
    jaw: Math.min(mw * 0.16, Math.max(0.008, clearance * 0.22)),
  };
}

function onLowerLip(index, y, seal) {
  if (LOWER_INNER.has(index) || LOWER_OUTER.has(index)) return true;
  if (UPPER_LIP.has(index)) return false;
  return y > seal;
}

function blendedShape(current, next, amount) {
  const from = shapeOf(current);
  const to = shapeOf(next || current);
  const mix = Math.max(0, Math.min(1, amount));
  const out = {};
  for (const key of Object.keys(from)) out[key] = from[key] * (1 - mix) + to[key] * mix;
  return out;
}

function follow(shown, target, dt, reduce) {
  const step = Math.max(0, dt);
  for (const key of Object.keys(target)) {
    const rising = target[key] > shown[key];
    let rate = 10;
    if (key === "jaw") rate = rising ? 7 : 5;
    else if (key === "press") rate = rising ? 28 : 22;
    else if (MOUTH_KEYS[key]) rate = rising ? 16 : 12;
    const ease = reduce && MOUTH_KEYS[key] ? 1 : 1 - Math.exp(-step * rate);
    shown[key] = lerp(shown[key], target[key], ease);
  }
}

export function englishVisemes(text) {
  const out = [];
  const s = text.toLowerCase();
  const vowel = (c) => "aeiou".includes(c);
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    const n = s[i + 1] || "";
    if (" \n\t".includes(c)) continue;
    if (",.;!?—-".includes(c)) {
      out.push("sil");
      continue;
    }
    if (c === "a") out.push("aa");
    else if (c === "e") out.push(n === "e" || n === "a" ? "I" : "E");
    else if (c === "i" || (c === "y" && !vowel(n))) out.push("I");
    else if (c === "o") out.push(n === "o" || n === "u" ? "U" : "O");
    else if (c === "u") out.push("U");
    else if (c === "w") out.push("U");
    else if (c === "r") out.push("RR");
    else if (c === "y") out.push("I");
    else if ("bpm".includes(c)) out.push("PP");
    else if (c === "f" || c === "v") out.push("FF");
    else if (c === "t" && n === "h") { out.push("TH"); i += 1; }
    else if ((c === "c" || c === "s") && n === "h") { out.push("CH"); i += 1; }
    else if ("sz".includes(c) || (c === "c" && n !== "h")) out.push("SS");
    else if ("td".includes(c)) out.push("DD");
    else if ("kg".includes(c)) out.push("kk");
    else if ("nl".includes(c)) out.push("nn");
    else if (c === "j") out.push("CH");
    else if (c === "q") out.push("kk");
    else if (c === "x") out.push("SS");
  }
  return out.length ? out : ["sil"];
}

export function pinyinVisemes(pinyin) {
  const initials = {
    b: "PP", p: "PP", m: "PP", f: "FF", d: "DD", t: "DD", n: "nn", l: "nn",
    g: "kk", k: "kk", h: "kk", j: "CH", q: "CH", x: "SS", r: "RR", z: "SS",
    c: "SS", s: "SS", y: "I", w: "U", zh: "CH", ch: "CH", sh: "CH",
  };
  const out = [];
  for (const raw of pinyin.toLowerCase().split(/\s+/)) {
    const syl = raw.replace(/[1-5]/g, "");
    if (!syl) continue;
    const ini = syl.match(/^(zh|ch|sh|b|p|m|f|d|t|n|l|g|k|h|j|q|x|r|z|c|s|y|w)/);
    const head = ini ? ini[1] : "";
    if (head && initials[head]) out.push(initials[head]);
    const fin = syl.slice(head.length);
    if (/iang|iong|uang|ang|ao|ua|ia/.test(fin)) out.push("aa");
    else if (/iong|ong|ou|uo/.test(fin)) out.push("O");
    else if (/eng|en|ei|ie|ui|ve/.test(fin)) out.push("E");
    else if (fin.includes("i")) out.push("I");
    else if (fin.includes("u") || fin.includes("v")) out.push("U");
    else if (fin.includes("o")) out.push("O");
    else if (fin.includes("e")) out.push("E");
    else if (fin.includes("a")) out.push("aa");
    else out.push("aa");
  }
  return out.length ? out : ["sil"];
}

function shapeOf(name) {
  return SHAPES[name] || SHAPES.sil;
}

export class Portrait {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: true,
      premultipliedAlpha: false,
      preserveDrawingBuffer: true,
    });
    if (!this.gl) throw new Error("WebGL is not available");
    this.mode = "idle";
    this.mood = "neutral";
    this.viseme = "sil";
    this.nextViseme = "sil";
    this.blend = 0;
    this.reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.lookTarget = 0;
    this.shown = { open: 0, round: 0, wide: 0, jaw: 0, press: 0, smile: 0.08, brow: 0, look: 0, nod: 0, blink: 0 };
    this.nextBlink = performance.now() + 800;
    this.blinkStart = -1;
    this._buildProgram();
  }

  async load(imageUrl, meshUrl) {
    const [mesh, image] = await Promise.all([
      fetch(meshUrl).then((r) => r.json()),
      loadImage(imageUrl),
    ]);
    this.rest = mesh.points;
    this.faceCount = mesh.faceCount;
    this.triangles = mesh.triangles;
    this.mouthLimits = mouthLimits(this.rest, this.faceCount, this.triangles);
    this.posed = this.rest.map((p) => [p[0], p[1]]);
    const gl = this.gl;
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    this.texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
    this.pos = new Float32Array(this.rest.length * 2);
    this.uv = new Float32Array(this.rest.length * 2);
    this.rest.forEach((p, i) => {
      this.uv[i * 2] = p[0];
      this.uv[i * 2 + 1] = 1 - p[1];
    });
    this.posBuf = gl.createBuffer();
    this.uvBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.uv, gl.STATIC_DRAW);
    this.indexBuf = gl.createBuffer();
    const idx = new Uint16Array(this.triangles.length * 3);
    this.triangles.forEach((t, i) => {
      idx[i * 3] = t[0];
      idx[i * 3 + 1] = t[1];
      idx[i * 3 + 2] = t[2];
    });
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.indexBuf);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
    this.indexCount = idx.length;
    this.resize();
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(2, Math.round(rect.width * dpr));
    const h = Math.max(2, Math.round(rect.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    if (this.overlay && (this.overlay.width !== this.canvas.width || this.overlay.height !== this.canvas.height)) {
      this.overlay.width = this.canvas.width;
      this.overlay.height = this.canvas.height;
    }
  }

  setMode(mode, mood) {
    this.mode = mode;
    if (mood) this.mood = mood;
  }

  setViseme(name, next, blend) {
    this.viseme = name || "sil";
    this.nextViseme = next || this.viseme;
    this.blend = Number.isFinite(blend) ? Math.max(0, Math.min(1, blend)) : 0;
  }

  setLook(x) {
    this.lookTarget = x;
  }

  frame(now, dt) {
    const mood = MOODS[this.mode === "listen" ? "listen" : this.mood] || MOODS.neutral;
    const speaking = this.mode === "speak";
    const shape = blendedShape(this.viseme, this.nextViseme, speaking ? this.blend || 0 : 0);
    const nodTarget = speaking || this.reduceMotion
      ? 0
      : this.mode === "listen"
        ? Math.sin(now / 620) * 0.045
        : Math.sin(now / 900) * 0.012;
    if (this.blinkStart < 0 && now >= this.nextBlink) {
      this.blinkStart = now;
      this.nextBlink = now + 2400 + Math.random() * 2800;
    }
    let blink = 0;
    if (this.blinkStart >= 0) {
      const age = now - this.blinkStart;
      if (age < 150) blink = Math.sin((age / 150) * Math.PI);
      else this.blinkStart = -1;
    }
    // Speak mode is mouth-only: no smile/brow/cheek/chin so the brow mesh stays sharp.
    const smile = speaking ? 0 : mood.smile;
    const target = {
      open: shape.open,
      round: shape.round,
      wide: shape.wide,
      jaw: speaking ? 0 : shape.jaw,
      press: shape.press,
      smile,
      brow: speaking ? 0 : mood.brow,
      look: this.lookTarget,
      nod: nodTarget,
      blink,
    };
    follow(this.shown, target, dt, this.reduceMotion);
    this._pose();
    this._draw();
    this._teeth();
  }

  _pose() {
    const rest = this.rest;
    const pts = this.posed;
    const n = this.faceCount;
    for (let i = 0; i < rest.length; i++) {
      pts[i][0] = rest[i][0];
      pts[i][1] = rest[i][1];
    }
    const speaking = this.mode === "speak";
    const limits = this.mouthLimits || mouthLimits(rest, n, this.triangles);
    const mw = limits.mw;
    const cx = (rest[61][0] + rest[291][0]) / 2;
    const cy = (rest[13][1] + rest[14][1]) / 2;
    const s = this.shown;
    // Closed photos keep the inner lip on one line. Split that line by landmark
    // so the upper lip rises and the lower lip drops. During speech only the
    // lip landmarks are deformed; the chin, cheeks, brows, and head stay still.
    const shut = 1 - s.press * 0.92;
    const U = s.open * limits.up * shut;
    const D = s.open * limits.down * shut;
    const chinDrop = s.jaw * (limits.jaw || limits.down * 0.45) * shut;
    const lipTop = limits.lipTop;
    const nose = limits.nose;
    const chinY = limits.chin;
    const lowerY = rest[17][1];
    for (let i = 0; i < n; i++) {
      const p = rest[i];
      const dx = (p[0] - cx) / mw;
      const y = p[1];
      const hx = smoothstep(1 - Math.abs(dx) / 1.35);
      const lip = isLip(i);
      // During speech, never move points above the upper-lip edge (keeps brows sharp).
      const aboveLip = speaking && y < lipTop - 1e-4;
      let dy = 0;
      if ((!speaking || lip) && !aboveLip) {
        if (!onLowerLip(i, y, cy)) {
          // Idle can fade toward the nose; speak mode only moves the lip sheet itself.
          const fade = speaking
            ? 1
            : (y >= lipTop ? 1 : smoothstep((y - nose) / Math.max(0.02, lipTop - nose)));
          dy = -U * fade * hx;
        } else if (y <= lowerY) {
          dy = D * hx;
        } else if (!speaking) {
          const span = Math.max(0.02, chinY - lowerY);
          const jawT = Math.min(1, (y - lowerY) / span);
          let mag = D * (1 - jawT) + chinDrop * jawT;
          if (y > chinY) mag *= Math.max(0, 1 - (y - chinY) / limits.clearance);
          dy = mag * hx;
        } else {
          // Speak: lower lip only — no chin drop that pulls cheek/jaw mesh.
          dy = D * hx;
        }
      }
      const side = dx >= 0 ? 1 : -1;
      const corner = smoothstep(Math.max(0, Math.abs(dx) - 0.2) / 0.45);
      let dxPx = 0;
      let smileDy = 0;
      if ((!speaking || lip) && !aboveLip) {
        dxPx = side * s.wide * mw * 0.05 * corner - side * s.round * mw * 0.2 * corner;
        if (!speaking) {
          smileDy = s.smile * mw * 0.05 * corner;
          dxPx += side * s.smile * mw * 0.02 * corner;
        }
      }
      dy -= smileDy;
      pts[i][0] = p[0] + dxPx;
      pts[i][1] = p[1] + dy;
    }
    this.mouth = { cx, cy, mw };
    if (!speaking) {
      const lift = s.smile * mw * 0.12;
      for (const i of CHEEK_L.concat(CHEEK_R)) pts[i][1] -= lift;
      for (const i of BROW_L.concat(BROW_R)) pts[i][1] = rest[i][1] - s.brow * mw * 0.32;
      pts[107][1] -= s.brow * mw * 0.12;
      pts[336][1] -= s.brow * mw * 0.12;
    }
    this._blink(LID_UPPER_L, LID_LOWER_L, s.blink);
    this._blink(LID_UPPER_R, LID_LOWER_R, s.blink);
    const look = s.look * mw * 0.22;
    for (const i of IRIS_L.concat(IRIS_R)) pts[i][0] = rest[i][0] + look;
    if (!speaking) {
      const pivotX = (rest[234][0] + rest[454][0]) / 2;
      const pivotY = rest[152][1] + mw * 1.1;
      const c = Math.cos(s.nod);
      const sn = Math.sin(s.nod);
      for (let i = 0; i < n; i++) {
        const x = pts[i][0] - pivotX;
        const y = pts[i][1] - pivotY;
        pts[i][0] = pivotX + x * c - y * sn;
        pts[i][1] = pivotY + x * sn + y * c;
      }
    }
  }

  _blink(upper, lower, amount) {
    if (amount <= 0.001) return;
    const rest = this.rest;
    const pts = this.posed;
    for (let k = 0; k < upper.length; k++) {
      const u = upper[k];
      const l = lower[k];
      pts[u][1] = lerp(pts[u][1], rest[l][1], amount * 0.92);
    }
  }

  _draw() {
    const gl = this.gl;
    const pts = this.posed;
    for (let i = 0; i < pts.length; i++) {
      this.pos[i * 2] = pts[i][0] * 2 - 1;
      this.pos[i * 2 + 1] = 1 - pts[i][1] * 2;
    }
    gl.useProgram(this.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.pos, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(this.aPos);
    gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuf);
    gl.enableVertexAttribArray(this.aUv);
    gl.vertexAttribPointer(this.aUv, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.indexBuf);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.uniform1i(this.uTex, 0);
    gl.drawElements(gl.TRIANGLES, this.indexCount, gl.UNSIGNED_SHORT, 0);
  }

  _teeth() {
    const open = this.shown.open * (1 - this.shown.press * 0.9);
    const canvas = this.overlay;
    const ctx = canvas.getContext("2d");
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (!ctx || !this.posed || !this.mouth || !w || !h) return;
    ctx.clearRect(0, 0, w, h);
    if (open < 0.1) return;
    const pts = this.posed;
    const loop = INNER_LIP.map((index) => pts[index]);
    let cx = 0;
    let cy = 0;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of loop) {
      cx += p[0];
      cy += p[1];
      minY = Math.min(minY, p[1]);
      maxY = Math.max(maxY, p[1]);
    }
    cx /= loop.length;
    cy /= loop.length;
    if (maxY - minY < this.mouth.mw * 0.08) return;
    const inset = 0.9;
    const poly = loop.map((p) => [cx + (p[0] - cx) * inset, cy + (p[1] - cy) * inset]);
    const top = Math.min(...poly.map((p) => p[1])) * h;
    const bot = Math.max(...poly.map((p) => p[1])) * h;
    ctx.beginPath();
    const count = poly.length;
    const at = (index) => {
      const p = poly[(index + count) % count];
      return [p[0] * w, p[1] * h];
    };
    const start = at(0);
    ctx.moveTo(start[0], start[1]);
    for (let i = 0; i < count; i++) {
      const cur = at(i);
      const nxt = at(i + 1);
      ctx.quadraticCurveTo(cur[0], cur[1], (cur[0] + nxt[0]) / 2, (cur[1] + nxt[1]) / 2);
    }
    ctx.closePath();
    const shade = ctx.createLinearGradient(0, top, 0, bot);
    shade.addColorStop(0, "rgba(104, 52, 58, 0.98)");
    shade.addColorStop(0.2, "rgba(48, 18, 24, 0.98)");
    shade.addColorStop(1, "rgba(22, 10, 14, 0.99)");
    ctx.fillStyle = shade;
    ctx.fill();
    if (open > 0.34) {
      const upper = poly.slice(0, 11);
      const tooth = Math.max(1.2, (bot - top) * 0.2);
      ctx.save();
      ctx.clip();
      ctx.beginPath();
      upper.forEach((p, i) => {
        const x = p[0] * w;
        const y = p[1] * h + tooth * 0.08;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      for (let i = upper.length - 1; i >= 0; i--) ctx.lineTo(upper[i][0] * w, upper[i][1] * h + tooth);
      ctx.closePath();
      ctx.fillStyle = "rgba(246, 242, 234, 0.94)";
      ctx.fill();
      ctx.strokeStyle = "rgba(186, 170, 160, 0.65)";
      ctx.lineWidth = Math.max(1, tooth * 0.08);
      for (let k = 1; k <= 5; k++) {
        const p = upper[Math.round((upper.length - 1) * k / 6)];
        ctx.beginPath();
        ctx.moveTo(p[0] * w, p[1] * h + tooth * 0.12);
        ctx.lineTo(p[0] * w, p[1] * h + tooth * 0.9);
        ctx.stroke();
      }
      ctx.restore();
    }
    const gl = this.gl;
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.bindTexture(gl.TEXTURE_2D, this.teethTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvas);
    const fan = new Float32Array((poly.length + 2) * 2);
    const uvs = new Float32Array((poly.length + 2) * 2);
    const put = (slot, x, y) => {
      fan[slot * 2] = x * 2 - 1;
      fan[slot * 2 + 1] = 1 - y * 2;
      uvs[slot * 2] = x;
      uvs[slot * 2 + 1] = 1 - y;
    };
    const pcx = poly.reduce((sum, p) => sum + p[0], 0) / poly.length;
    const pcy = poly.reduce((sum, p) => sum + p[1], 0) / poly.length;
    put(0, pcx, pcy);
    for (let i = 0; i <= poly.length; i++) {
      const p = poly[i % poly.length];
      put(i + 1, p[0], p[1]);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, this.fanPos);
    gl.bufferData(gl.ARRAY_BUFFER, fan, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(this.aPos);
    gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.fanUv);
    gl.bufferData(gl.ARRAY_BUFFER, uvs, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(this.aUv);
    gl.vertexAttribPointer(this.aUv, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_FAN, 0, poly.length + 2);
    gl.disable(gl.BLEND);
  }

  _buildProgram() {
    const gl = this.gl;
    const vs = compile(gl, gl.VERTEX_SHADER, `
      attribute vec2 a_pos;
      attribute vec2 a_uv;
      varying vec2 v_uv;
      void main() {
        v_uv = a_uv;
        gl_Position = vec4(a_pos, 0.0, 1.0);
      }`);
    const fs = compile(gl, gl.FRAGMENT_SHADER, `
      precision mediump float;
      uniform sampler2D u_tex;
      varying vec2 v_uv;
      void main() {
        gl_FragColor = texture2D(u_tex, v_uv);
      }`);
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "shader link failed");
    }
    this.program = program;
    this.aPos = gl.getAttribLocation(program, "a_pos");
    this.aUv = gl.getAttribLocation(program, "a_uv");
    this.uTex = gl.getUniformLocation(program, "u_tex");
    this.overlay = document.createElement("canvas");
    this.teethTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.teethTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.fanPos = gl.createBuffer();
    this.fanUv = gl.createBuffer();
    const resizeOverlay = () => {
      this.overlay.width = this.canvas.width || 2;
      this.overlay.height = this.canvas.height || 2;
    };
    resizeOverlay();
    this._resizeOverlay = resizeOverlay;
  }
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  return shader;
}

export class IllustratedPortrait {
  constructor(canvas, partner) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.partner = partner;
    this.palette = partner.palette || { bg: "#d7dee8", hair: "#2a211c", skin: "#f0c7b0", shirt: "#355070" };
    this.mode = "idle";
    this.mood = "neutral";
    this.viseme = "sil";
    this.nextViseme = "sil";
    this.blend = 0;
    this.lookTarget = 0;
    this.reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.shown = { open: 0, round: 0, wide: 0, jaw: 0, press: 0, smile: 0.08, brow: 0, blink: 0, nod: 0 };
    this.nextBlink = performance.now() + 800;
    this.blinkStart = -1;
  }

  async load() {}

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(2, Math.round(rect.width * dpr));
    const h = Math.max(2, Math.round(rect.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
  }

  setMode(mode, mood) {
    this.mode = mode;
    if (mood) this.mood = mood;
  }

  setViseme(name, next, blend) {
    this.viseme = name || "sil";
    this.nextViseme = next || this.viseme;
    this.blend = Number.isFinite(blend) ? Math.max(0, Math.min(1, blend)) : 0;
  }

  setLook(x) {
    this.lookTarget = x;
  }

  frame(now, dt) {
    const mood = MOODS[this.mode === "listen" ? "listen" : this.mood] || MOODS.neutral;
    const speaking = this.mode === "speak";
    const shape = blendedShape(this.viseme, this.nextViseme, speaking ? this.blend || 0 : 0);
    if (this.blinkStart < 0 && now >= this.nextBlink) {
      this.blinkStart = now;
      this.nextBlink = now + 2400 + Math.random() * 2800;
    }
    let blink = 0;
    if (this.blinkStart >= 0) {
      const age = now - this.blinkStart;
      if (age < 150) blink = Math.sin((age / 150) * Math.PI);
      else this.blinkStart = -1;
    }
    const nod = this.reduceMotion || speaking ? 0 : this.mode === "listen" ? Math.sin(now / 620) * 0.045 : 0;
    const smile = speaking ? 0 : mood.smile;
    const target = {
      open: shape.open,
      round: shape.round,
      wide: shape.wide,
      jaw: speaking ? 0 : shape.jaw,
      press: shape.press,
      smile,
      brow: speaking ? 0 : mood.brow,
      blink,
      nod,
    };
    follow(this.shown, target, dt, this.reduceMotion);
    this._draw();
  }

  _draw() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (!ctx || !w || !h) return;
    const p = this.palette;
    const s = this.shown;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = p.bg;
    ctx.fillRect(0, 0, w, h);
    const cx = w * 0.5;
    const cy = h * (0.46 + s.nod);
    const head = Math.min(w, h) * 0.34;
    ctx.fillStyle = p.shirt || "#355070";
    ctx.beginPath();
    ctx.ellipse(cx, h * 0.92, head * 1.15, head * 0.85, 0, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = p.hair;
    ctx.beginPath();
    ctx.ellipse(cx, cy - head * 0.08, head * 1.05, head * 1.18, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = p.skin;
    ctx.beginPath();
    ctx.ellipse(cx, cy, head * 0.86, head * 0.98, 0, 0, Math.PI * 2);
    ctx.fill();
    const eyeY = cy - head * 0.08;
    const eyeX = head * 0.32;
    const look = this.lookTarget * head * 0.04;
    ctx.fillStyle = "#1d2430";
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.ellipse(cx + side * eyeX + look, eyeY, head * 0.07, head * 0.08 * (1 - s.blink), 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.strokeStyle = p.hair;
    ctx.lineWidth = Math.max(2, head * 0.035);
    const browLift = -s.brow * head * 0.08;
    ctx.beginPath();
    ctx.moveTo(cx - eyeX - head * 0.12, eyeY - head * 0.16 + browLift);
    ctx.quadraticCurveTo(cx - eyeX, eyeY - head * 0.24 + browLift, cx - eyeX + head * 0.14, eyeY - head * 0.14 + browLift * 0.4);
    ctx.moveTo(cx + eyeX + head * 0.12, eyeY - head * 0.16 + browLift);
    ctx.quadraticCurveTo(cx + eyeX, eyeY - head * 0.24 + browLift, cx + eyeX - head * 0.14, eyeY - head * 0.14 + browLift * 0.4);
    ctx.stroke();
    const jawDrop = s.open * s.jaw * head * 0.05 * (1 - s.press);
    const mouthY = cy + head * 0.36 + jawDrop;
    const mouthW = head * (0.28 + s.wide * 0.08 - s.round * 0.06 + s.smile * 0.04);
    const openH = head * (0.02 + s.open * 0.22) * (1 - s.press * 0.92);
    const smile = s.smile * head * 0.05;
    if (s.press > 0.65 || s.open < 0.1) {
      ctx.strokeStyle = "#a85a68";
      ctx.lineWidth = Math.max(2, head * 0.03);
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(cx - mouthW, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + smile, cx + mouthW, mouthY);
      ctx.stroke();
    } else {
      const top = mouthY - openH * 0.28;
      const bot = mouthY + openH * 0.72;
      ctx.fillStyle = "#4a242c";
      ctx.beginPath();
      ctx.moveTo(cx - mouthW, mouthY);
      ctx.quadraticCurveTo(cx, top, cx + mouthW, mouthY);
      ctx.quadraticCurveTo(cx, bot, cx - mouthW, mouthY);
      ctx.fill();
      if (s.open > 0.34) {
        ctx.fillStyle = "#f4f0e8";
        const tooth = Math.max(2, openH * 0.16);
        ctx.fillRect(cx - mouthW * 0.62, top + openH * 0.18, mouthW * 1.24, tooth);
      }
    }
    ctx.fillStyle = "rgba(15, 23, 42, 0.72)";
    ctx.font = `${Math.round(head * 0.16)}px sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText("Illustrated", cx, h * 0.08);
  }
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Could not load ${url}`));
    image.src = url;
  });
}
