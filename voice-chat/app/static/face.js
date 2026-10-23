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

const SHAPES = {
  sil: { open: 0.04, round: 0, wide: 0.04, jaw: 0, press: 0 },
  aa: { open: 1, round: 0.06, wide: 0.12, jaw: 1, press: 0 },
  E: { open: 0.62, round: 0, wide: 0.78, jaw: 0.5, press: 0 },
  I: { open: 0.36, round: 0, wide: 0.95, jaw: 0.22, press: 0 },
  O: { open: 0.9, round: 0.92, wide: 0, jaw: 0.72, press: 0 },
  U: { open: 0.5, round: 1, wide: 0, jaw: 0.34, press: 0 },
  PP: { open: 0, round: 0.08, wide: 0, jaw: 0, press: 1 },
  FF: { open: 0.2, round: 0.04, wide: 0.16, jaw: 0.12, press: 0.15 },
  TH: { open: 0.4, round: 0, wide: 0.22, jaw: 0.28, press: 0 },
  DD: { open: 0.46, round: 0, wide: 0.08, jaw: 0.36, press: 0 },
  kk: { open: 0.55, round: 0.1, wide: 0, jaw: 0.58, press: 0 },
  CH: { open: 0.4, round: 0.55, wide: 0, jaw: 0.3, press: 0 },
  SS: { open: 0.22, round: 0, wide: 0.42, jaw: 0.12, press: 0 },
  nn: { open: 0.28, round: 0, wide: 0.06, jaw: 0.18, press: 0 },
  RR: { open: 0.38, round: 0.42, wide: 0, jaw: 0.26, press: 0 },
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
    up: Math.min(mw * 0.36, noseSpan * 0.62),
    down: Math.min(mw * 0.62, Math.max(0.018, clearance * 0.5)),
  };
}

function follow(shown, target, dt, reduce) {
  const step = Math.max(0, dt);
  for (const key of Object.keys(target)) {
    const rising = target[key] > shown[key];
    const rate = MOUTH_KEYS[key] ? (rising ? 36 : 24) : 12;
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

  setViseme(name) {
    this.viseme = name;
  }

  setLook(x) {
    this.lookTarget = x;
  }

  frame(now, dt) {
    const mood = MOODS[this.mode === "listen" ? "listen" : this.mood] || MOODS.neutral;
    const shape = shapeOf(this.viseme);
    const speaking = this.mode === "speak";
    const nodTarget = this.reduceMotion
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
    const smile = speaking ? Math.min(mood.smile, 0.26) : mood.smile;
    const target = {
      open: shape.open,
      round: shape.round,
      wide: shape.wide,
      jaw: shape.jaw,
      press: shape.press,
      smile,
      brow: mood.brow,
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
    const limits = this.mouthLimits || mouthLimits(rest, n, this.triangles);
    const mw = limits.mw;
    const cx = (rest[61][0] + rest[291][0]) / 2;
    const cy = (rest[13][1] + rest[14][1]) / 2;
    const s = this.shown;
    const press = s.press;
    // Shift each lip as one sheet. Interior lip points used to stay put, so a
    // closed photograph never opened. Travel is capped by the nose-to-lip span
    // and the chin-to-background gap so the mesh does not fold.
    const shut = 1 - press * 0.92;
    const U = s.open * limits.up * shut;
    const D = s.open * Math.max(s.jaw, 0.28) * limits.down * shut;
    const lipTop = limits.lipTop;
    const nose = limits.nose;
    const chinY = limits.chin;
    for (let i = 0; i < n; i++) {
      const p = rest[i];
      const dx = (p[0] - cx) / mw;
      const y = p[1];
      const hx = smoothstep(1 - Math.abs(dx) / 1.85);
      let dy = 0;
      if (y <= cy) {
        const fade = y >= lipTop ? 1 : smoothstep((y - nose) / Math.max(0.02, lipTop - nose));
        dy = -U * fade * hx;
      } else if (y <= chinY) {
        dy = D * hx;
      } else {
        dy = D * hx * Math.max(0, 1 - (y - chinY) / limits.clearance);
      }
      const band = Math.max(0, 1 - Math.abs(y - cy) / (mw * 1.15));
      const side = dx >= 0 ? 1 : -1;
      let dxPx = side * s.wide * mw * 0.12 * band * smoothstep(Math.min(1, Math.abs(dx)));
      dxPx += -dx * mw * s.round * 0.22 * band * hx;
      const corner = smoothstep(Math.max(0, Math.abs(dx) - 0.36) / 0.45);
      dy -= s.smile * mw * 0.05 * corner * band;
      dxPx += side * s.smile * mw * 0.02 * corner;
      if (press > 0.55 && Math.abs(dx) < 0.72 && Math.abs(y - cy) < 0.055) dy *= 1 - 0.75 * press;
      pts[i][0] = p[0] + dxPx;
      pts[i][1] = p[1] + dy;
    }
    this.mouth = { cx, cy, mw };
    const lift = s.smile * mw * 0.12;
    for (const i of CHEEK_L.concat(CHEEK_R)) pts[i][1] -= lift;
    for (const i of BROW_L.concat(BROW_R)) pts[i][1] = rest[i][1] - s.brow * mw * 0.32;
    pts[107][1] -= s.brow * mw * 0.12;
    pts[336][1] -= s.brow * mw * 0.12;
    this._blink(LID_UPPER_L, LID_LOWER_L, s.blink);
    this._blink(LID_UPPER_R, LID_LOWER_R, s.blink);
    const look = s.look * mw * 0.22;
    for (const i of IRIS_L.concat(IRIS_R)) pts[i][0] = rest[i][0] + look;
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
    if (open < 0.08) return;
    const pts = this.posed;
    const mw = this.mouth.mw;
    const left = pts[61];
    const right = pts[291];
    const upper = pts[0];
    const lower = pts[17];
    const mx = (left[0] + right[0]) / 2;
    const span = Math.max(0.001, lower[1] - upper[1]);
    const rx = Math.hypot(right[0] - left[0], right[1] - left[1]) * (0.34 + this.shown.wide * 0.06 - this.shown.round * 0.1);
    const ry = Math.max(mw * 0.035, span * 0.34);
    const my = upper[1] + span * 0.48;
    const steps = 22;
    const poly = [];
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * Math.PI * 2;
      const sy = Math.sin(angle);
      poly.push([mx + Math.cos(angle) * rx, my + sy * ry * (sy > 0 ? 1.08 : 0.88)]);
    }
    ctx.beginPath();
    poly.forEach((p, i) => {
      const x = p[0] * w;
      const y = p[1] * h;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = "#241014";
    ctx.fill();
    ctx.save();
    ctx.clip();
    const top = (my - ry * 0.92) * h;
    const bot = (my + ry * 1.05) * h;
    const gap = Math.max(2, bot - top);
    const midX = mx * w;
    const toothW = rx * 2 * w * 0.72;
    if (open > 0.18) {
      ctx.fillStyle = "#f3f0e8";
      const toothH = Math.max(2, gap * 0.22);
      ctx.fillRect(midX - toothW / 2, top + gap * 0.06, toothW, toothH);
      ctx.fillStyle = "rgba(150, 126, 116, 0.55)";
      const teeth = 5;
      for (let i = 1; i < teeth; i++) {
        const x = midX - toothW / 2 + (toothW * i) / teeth;
        ctx.fillRect(x, top + gap * 0.08, Math.max(1, w * 0.0015), toothH * 0.75);
      }
    }
    ctx.fillStyle = "rgba(122, 58, 66, 0.9)";
    ctx.beginPath();
    ctx.ellipse(midX, top + gap * 0.72, toothW * 0.42, gap * 0.18, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
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

  setViseme(name) {
    this.viseme = name;
  }

  setLook(x) {
    this.lookTarget = x;
  }

  frame(now, dt) {
    const mood = MOODS[this.mode === "listen" ? "listen" : this.mood] || MOODS.neutral;
    const shape = SHAPES[this.viseme] || SHAPES.sil;
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
    const nod = this.reduceMotion ? 0 : this.mode === "listen" ? Math.sin(now / 620) * 0.045 : 0;
    const speaking = this.mode === "speak";
    const smile = speaking ? Math.min(mood.smile, 0.26) : mood.smile;
    const target = {
      open: shape.open,
      round: shape.round,
      wide: shape.wide,
      jaw: shape.jaw,
      press: shape.press,
      smile,
      brow: mood.brow,
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
    const jawDrop = s.open * s.jaw * head * 0.1 * (1 - s.press);
    const mouthY = cy + head * 0.34 + jawDrop;
    const mouthW = head * (0.3 + s.wide * 0.2 - s.round * 0.1 + s.smile * 0.05);
    const openH = head * (0.045 + s.open * 0.46) * (1 - s.press * 0.92);
    const smile = s.smile * head * 0.06;
    if (s.press > 0.65 || s.open < 0.08) {
      ctx.strokeStyle = "#a85a68";
      ctx.lineWidth = Math.max(2, head * 0.035);
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(cx - mouthW, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + smile * 1.4, cx + mouthW, mouthY);
      ctx.stroke();
    } else {
      ctx.fillStyle = "#3a1820";
      ctx.beginPath();
      ctx.ellipse(cx, mouthY - smile * 0.15, mouthW * (s.round > 0.6 ? 0.72 : 1), Math.max(head * 0.04, openH), 0, 0, Math.PI * 2);
      ctx.fill();
      if (s.open > 0.18) {
        ctx.fillStyle = "#f4f1ea";
        const toothW = mouthW * (1.15 - s.round * 0.35);
        const toothH = openH * 0.34;
        ctx.fillRect(cx - toothW / 2, mouthY - openH * 0.82, toothW, toothH);
      }
      ctx.fillStyle = s.open > 0.45 ? "#c2646c" : "#7a3a44";
      ctx.beginPath();
      ctx.ellipse(cx, mouthY + openH * 0.28, mouthW * 0.42, openH * 0.28, 0, 0, Math.PI * 2);
      ctx.fill();
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
