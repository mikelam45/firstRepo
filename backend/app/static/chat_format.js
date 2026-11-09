/* Functions-page assistant reply formatter. Builds DOM nodes from a safe subset. */
(function (global) {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var SERIES_COLORS = ["var(--green)", "var(--amber)", "var(--rust)", "var(--ink)", "var(--muted)"];
  var MEDIA_FENCE_RE = /```(chart|figure)[^\n]*\n([\s\S]*?)```/g;
  var MAX_FIGURE_ELEMENTS = 48;
  var MAX_POLYGON_POINTS = 16;
  var MAX_LABEL_CHARS = 48;
  var HEADING_RE = /^(#{1,3})\s+(.+)$/;
  var UL_RE = /^\s*[-*+]\s+(.+)$/;
  var OL_RE = /^\s*\d+\.\s+(.+)$/;
  var TABLE_SEP_RE = /^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/;
  var BOLD_RE = /\*\*([^*]+)\*\*/;
  var CODE_RE = /`([^`]+)`/;
  var LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/;

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isSafeHref(href) {
    return /^(https?:\/\/|\/api\/rag\/|\/api\/translation\/)/i.test(String(href || "").trim());
  }

  function parseChartFence(body) {
    var text = String(body == null ? "" : body).trim();
    if (!text) return null;
    var data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      return null;
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) return null;

    var type = data.type == null || data.type === "" ? "bar" : String(data.type).toLowerCase();
    if (type !== "bar" && type !== "line" && type !== "pie") return null;

    if (!Array.isArray(data.labels) || !data.labels.length) return null;
    var labels = [];
    for (var i = 0; i < data.labels.length; i += 1) {
      labels.push(String(data.labels[i]));
    }

    if (!Array.isArray(data.series) || !data.series.length) return null;
    var series = [];
    for (var s = 0; s < data.series.length; s += 1) {
      var row = data.series[s];
      if (!row || typeof row !== "object" || Array.isArray(row)) return null;
      if (!Array.isArray(row.values) || row.values.length !== labels.length) return null;
      var values = [];
      for (var v = 0; v < row.values.length; v += 1) {
        var number = typeof row.values[v] === "number" ? row.values[v] : Number(row.values[v]);
        if (!isFinite(number)) return null;
        values.push(number);
      }
      series.push({
        name: row.name == null ? "Series" : String(row.name),
        values: values,
      });
    }

    if (type === "pie") {
      series = [series[0]];
    }

    return {
      type: type,
      title: data.title == null ? "" : String(data.title),
      labels: labels,
      series: series,
      caption: data.caption == null ? "" : String(data.caption).slice(0, MAX_LABEL_CHARS),
    };
  }

  function finiteNumber(value) {
    var number = typeof value === "number" ? value : Number(value);
    return isFinite(number) ? number : null;
  }

  function clipLabel(value) {
    return String(value == null ? "" : value).trim().slice(0, MAX_LABEL_CHARS);
  }

  var MAX_CAPTION_CHARS = 180;

  function clipCaption(value) {
    return String(value == null ? "" : value).trim().slice(0, MAX_CAPTION_CHARS);
  }

  function withPart(item, row) {
    if (!item || !row) return item;
    var id = clipLabel(row.id || row.part);
    if (id) item.id = id;
    var match = clipLabel(row.match);
    if (match) item.match = match;
    var cap = clipCaption(row.caption || row.hint);
    if (cap) item.caption = cap;
    return item;
  }

  function parsePoint(value) {
    if (Array.isArray(value) && value.length >= 2) {
      var x = finiteNumber(value[0]);
      var y = finiteNumber(value[1]);
      if (x == null || y == null) return null;
      return [x, y];
    }
    if (value && typeof value === "object") {
      var px = finiteNumber(value.x);
      var py = finiteNumber(value.y);
      if (px == null || py == null) return null;
      return [px, py];
    }
    return null;
  }

  function parseFigureElement(row) {
    if (!row || typeof row !== "object" || Array.isArray(row)) return null;
    var kind = String(row.kind || row.type || "").trim().toLowerCase();
    if (kind === "text") kind = "label";
    if (kind === "line") kind = "segment";
    var item = { kind: kind };
    if (kind === "point") {
      var x = finiteNumber(row.x);
      var y = finiteNumber(row.y);
      if (x == null || y == null) {
        var at = parsePoint(row.at || row.point);
        if (!at) return null;
        x = at[0];
        y = at[1];
      }
      item.x = x;
      item.y = y;
      item.label = clipLabel(row.label);
      return withPart(item, row);
    }
    if (kind === "segment" || kind === "arrow") {
      var start = parsePoint(row.from || row.start);
      var end = parsePoint(row.to || row.end);
      if (!start || !end) return null;
      item.from = start;
      item.to = end;
      item.label = clipLabel(row.label);
      return withPart(item, row);
    }
    if (kind === "polygon") {
      if (!Array.isArray(row.points) || row.points.length < 3) return null;
      var points = [];
      for (var i = 0; i < row.points.length && points.length < MAX_POLYGON_POINTS; i += 1) {
        var point = parsePoint(row.points[i]);
        if (!point) return null;
        points.push(point);
      }
      if (points.length < 3) return null;
      var labels = [];
      if (Array.isArray(row.labels)) {
        for (var L = 0; L < row.labels.length && L < points.length; L += 1) {
          labels.push(clipLabel(row.labels[L]));
        }
      }
      item.points = points;
      item.labels = labels;
      item.fill = row.fill !== false;
      return withPart(item, row);
    }
    if (kind === "circle") {
      var cx = finiteNumber(row.cx);
      var cy = finiteNumber(row.cy);
      var radius = finiteNumber(row.r != null ? row.r : row.radius);
      if (cx == null || cy == null || radius == null || radius <= 0) {
        var centre = parsePoint(row.center || row.centre || row.at);
        if (!centre || radius == null || radius <= 0) return null;
        cx = centre[0];
        cy = centre[1];
      }
      item.cx = cx;
      item.cy = cy;
      item.r = radius;
      item.label = clipLabel(row.label);
      return withPart(item, row);
    }
    if (kind === "arc" || kind === "sector") {
      var acx = finiteNumber(row.cx);
      var acy = finiteNumber(row.cy);
      var ar = finiteNumber(row.r != null ? row.r : row.radius);
      var aStart = finiteNumber(row.start != null ? row.start : row.start_deg);
      var aEnd = finiteNumber(row.end != null ? row.end : row.end_deg);
      if (acx == null || acy == null || ar == null || ar <= 0 || aStart == null || aEnd == null) {
        var aCentre = parsePoint(row.center || row.centre || row.at);
        if (!aCentre || ar == null || ar <= 0 || aStart == null || aEnd == null) return null;
        acx = aCentre[0];
        acy = aCentre[1];
      }
      item.cx = acx;
      item.cy = acy;
      item.r = ar;
      item.start = aStart;
      item.end = aEnd;
      item.label = clipLabel(row.label);
      if (kind === "sector") item.fill = row.fill !== false;
      return withPart(item, row);
    }
    if (kind === "angle") {
      var vertex = parsePoint(row.at || row.vertex);
      var fromPt = parsePoint(row.from || row.start);
      var toPt = parsePoint(row.to || row.end);
      if (!vertex || !fromPt || !toPt) return null;
      item.at = vertex;
      item.from = fromPt;
      item.to = toPt;
      item.label = clipLabel(row.label);
      item.right = !!(row.right || row.right_angle);
      return withPart(item, row);
    }
    if (kind === "label") {
      var lx = finiteNumber(row.x);
      var ly = finiteNumber(row.y);
      if (lx == null || ly == null) {
        var loc = parsePoint(row.at);
        if (!loc) return null;
        lx = loc[0];
        ly = loc[1];
      }
      var text = clipLabel(row.text || row.label);
      if (!text) return null;
      item.x = lx;
      item.y = ly;
      item.text = text;
      return withPart(item, row);
    }
    return null;
  }

  function parseFigureSpec(body) {
    var data = body;
    if (typeof body === "string") {
      var text = String(body || "").trim();
      if (!text) return null;
      try {
        data = JSON.parse(text);
      } catch (error) {
        return null;
      }
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) return null;
    var type = data.type == null || data.type === "" ? "geometry" : String(data.type).toLowerCase();
    if (type !== "geometry" && type !== "coordinate" && type !== "number_line" && type !== "chart") {
      return null;
    }
    var title = clipLabel(data.title);
    var caption = clipCaption(data.caption);
    if (type === "chart") {
      var payload = {};
      Object.keys(data).forEach(function (key) { payload[key] = data[key]; });
      if (String(payload.type || "").toLowerCase() === "chart") payload.type = "bar";
      var chart = parseChartFence(JSON.stringify(payload));
      if (!chart) return null;
      chart.caption = caption;
      return chart;
    }
    if (type === "number_line") {
      var low = finiteNumber(data.min);
      var high = finiteNumber(data.max);
      if (low == null || high == null || low === high) return null;
      if (low > high) {
        var swap = low;
        low = high;
        high = swap;
      }
      var marks = [];
      var marksRaw = data.marks || data.ticks;
      if (Array.isArray(marksRaw)) {
        for (var m = 0; m < marksRaw.length && marks.length < 24; m += 1) {
          var mark = finiteNumber(marksRaw[m]);
          if (mark != null) marks.push(mark);
        }
      }
      var linePoints = [];
      if (Array.isArray(data.points)) {
        for (var p = 0; p < data.points.length && linePoints.length < 16; p += 1) {
          var row = data.points[p];
          if (row && typeof row === "object" && !Array.isArray(row)) {
            var value = finiteNumber(row.value != null ? row.value : row.x);
            if (value == null) continue;
            linePoints.push({ value: value, label: clipLabel(row.label) });
          } else {
            var raw = finiteNumber(row);
            if (raw != null) linePoints.push({ value: raw, label: "" });
          }
        }
      }
      return { type: type, title: title, caption: caption, min: low, max: high, marks: marks, points: linePoints };
    }
    var elements = [];
    if (Array.isArray(data.elements)) {
      for (var e = 0; e < data.elements.length && elements.length < MAX_FIGURE_ELEMENTS; e += 1) {
        var item = parseFigureElement(data.elements[e]);
        if (item) elements.push(item);
      }
    }
    if (!elements.length) return null;
    var spec = { type: type, title: title, caption: caption, elements: elements };
    var axesSrc = data.axes && typeof data.axes === "object" ? data.axes : data;
    var xmin = finiteNumber(axesSrc.xmin);
    var xmax = finiteNumber(axesSrc.xmax);
    var ymin = finiteNumber(axesSrc.ymin);
    var ymax = finiteNumber(axesSrc.ymax);
    if (xmin != null && xmax != null && ymin != null && ymax != null && xmin !== xmax && ymin !== ymax) {
      spec.axes = {
        xmin: Math.min(xmin, xmax),
        xmax: Math.max(xmin, xmax),
        ymin: Math.min(ymin, ymax),
        ymax: Math.max(ymin, ymax),
      };
    }
    var hint = clipCaption(data.hint);
    if (hint) spec.hint = hint;
    var actions = [];
    if (Array.isArray(data.actions)) {
      for (var a = 0; a < data.actions.length && actions.length < 8; a += 1) {
        var act = data.actions[a];
        if (!act || typeof act !== "object") continue;
        var actLabel = clipLabel(act.label || act.id);
        if (!actLabel) continue;
        var highlight = [];
        var parts = act.highlight || act.parts;
        if (Array.isArray(parts)) {
          for (var h = 0; h < parts.length && highlight.length < 16; h += 1) {
            var token = clipLabel(parts[h]);
            if (token) highlight.push(token);
          }
        }
        actions.push({
          id: clipLabel(act.id || actLabel),
          label: actLabel,
          highlight: highlight,
          caption: clipCaption(act.caption),
        });
      }
    }
    if (actions.length) spec.actions = actions;
    var hasIds = false;
    for (var ei = 0; ei < elements.length; ei += 1) {
      if (elements[ei].id) { hasIds = true; break; }
    }
    if (data.interactive || actions.length || hasIds) spec.interactive = true;
    return spec;
  }

  function isTableSeparator(line) {
    return TABLE_SEP_RE.test(String(line || ""));
  }

  function splitTableRow(line) {
    var trimmed = String(line || "").trim();
    if (trimmed.charAt(0) === "|") trimmed = trimmed.slice(1);
    if (trimmed.charAt(trimmed.length - 1) === "|") trimmed = trimmed.slice(0, -1);
    return trimmed.split("|").map(function (cell) {
      return cell.trim();
    });
  }

  function looksLikeTableRow(line) {
    if (!line || line.indexOf("|") === -1 || isTableSeparator(line)) return false;
    return splitTableRow(line).length >= 2;
  }

  function appendInline(parent, text) {
    var remaining = String(text == null ? "" : text);
    while (remaining) {
      var bold = BOLD_RE.exec(remaining);
      var code = CODE_RE.exec(remaining);
      var link = LINK_RE.exec(remaining);
      var next = null;
      if (bold) next = { type: "bold", match: bold };
      if (code && (!next || code.index < next.match.index)) next = { type: "code", match: code };
      if (link && (!next || link.index < next.match.index)) next = { type: "link", match: link };
      if (!next) {
        parent.appendChild(document.createTextNode(remaining));
        return;
      }
      if (next.match.index > 0) {
        parent.appendChild(document.createTextNode(remaining.slice(0, next.match.index)));
      }
      if (next.type === "bold") {
        var strong = document.createElement("strong");
        strong.textContent = next.match[1];
        parent.appendChild(strong);
      } else if (next.type === "code") {
        var codeEl = document.createElement("code");
        codeEl.textContent = next.match[1];
        parent.appendChild(codeEl);
      } else {
        var href = String(next.match[2] || "").trim();
        if (isSafeHref(href)) {
          var anchor = document.createElement("a");
          anchor.href = href;
          anchor.textContent = next.match[1];
          if (/^https?:/i.test(href)) {
            anchor.target = "_blank";
            anchor.rel = "noopener noreferrer";
          }
          parent.appendChild(anchor);
        } else {
          parent.appendChild(document.createTextNode(next.match[0]));
        }
      }
      remaining = remaining.slice(next.match.index + next.match[0].length);
    }
  }

  function markdownTableToHtml(markdown) {
    var lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n").filter(function (line) {
      return line.trim();
    });
    if (lines.length < 2 || !isTableSeparator(lines[1])) return null;
    var headers = splitTableRow(lines[0]);
    if (!headers.length) return null;
    var table = document.createElement("table");
    var thead = document.createElement("thead");
    var headRow = document.createElement("tr");
    for (var h = 0; h < headers.length; h += 1) {
      var th = document.createElement("th");
      appendInline(th, headers[h]);
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    for (var r = 2; r < lines.length; r += 1) {
      if (isTableSeparator(lines[r])) continue;
      var cells = splitTableRow(lines[r]);
      var tr = document.createElement("tr");
      for (var c = 0; c < headers.length; c += 1) {
        var td = document.createElement("td");
        appendInline(td, c < cells.length ? cells[c] : "");
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
  }

  function splitMediaFences(text) {
    var src = String(text || "");
    var parts = [];
    var last = 0;
    var match;
    MEDIA_FENCE_RE.lastIndex = 0;
    while ((match = MEDIA_FENCE_RE.exec(src))) {
      if (match.index > last) {
        parts.push({ kind: "md", text: src.slice(last, match.index) });
      }
      parts.push({ kind: match[1], text: match[2], raw: match[0] });
      last = match.index + match[0].length;
    }
    if (last < src.length) {
      parts.push({ kind: "md", text: src.slice(last) });
    }
    return parts;
  }

  function formatTick(value) {
    if (!isFinite(value)) return "";
    if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.01)) {
      return String(Number(value.toPrecision(3)));
    }
    if (Math.abs(value - Math.round(value)) < 1e-9) return String(Math.round(value));
    return String(Math.round(value * 100) / 100);
  }

  function truncateLabel(text, max) {
    var value = String(text || "");
    if (value.length <= max) return value;
    return value.slice(0, Math.max(0, max - 1)) + "…";
  }

  function svgEl(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (attrs[key] != null) node.setAttribute(key, String(attrs[key]));
      });
    }
    return node;
  }

  function svgText(attrs, value) {
    var node = svgEl("text", attrs);
    node.textContent = value == null ? "" : String(value);
    return node;
  }

  function drawLegend(svg, series, x, y) {
    var offset = 0;
    for (var i = 0; i < series.length; i += 1) {
      var color = SERIES_COLORS[i % SERIES_COLORS.length];
      svg.appendChild(svgEl("rect", {
        x: x + offset,
        y: y - 8,
        width: 8,
        height: 8,
        fill: color,
      }));
      var label = svgText({
        x: x + offset + 11,
        y: y,
        fill: "var(--muted)",
        "font-size": "11",
      }, truncateLabel(series[i].name, 18));
      svg.appendChild(label);
      offset += 14 + Math.min(String(series[i].name || "").length, 18) * 6.2;
    }
  }

  function yScale(min, max, plotTop, plotH) {
    var range = max - min || 1;
    return function (value) {
      return plotTop + ((max - value) / range) * plotH;
    };
  }

  function drawAxisChart(spec) {
    var width = 560;
    var height = 320;
    var pad = { top: 44, right: 18, bottom: 52, left: 52 };
    var plotW = width - pad.left - pad.right;
    var plotH = height - pad.top - pad.bottom;
    var svg = svgEl("svg", {
      class: "chat-chart",
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": spec.title || spec.type + " chart",
    });
    svg.appendChild(svgEl("rect", {
      width: width,
      height: height,
      fill: "var(--card)",
      rx: 8,
    }));
    if (spec.title) {
      svg.appendChild(svgText({
        x: width / 2,
        y: 20,
        "text-anchor": "middle",
        fill: "var(--ink)",
        "font-size": "14",
        "font-weight": "650",
      }, spec.title));
    }
    if (spec.series.length) {
      drawLegend(svg, spec.series, pad.left, spec.title ? 36 : 20);
    }

    var values = [];
    spec.series.forEach(function (row) {
      row.values.forEach(function (value) { values.push(value); });
    });
    var max = Math.max.apply(null, values.concat([0]));
    var min = Math.min.apply(null, values.concat([0]));
    if (max === min) max = min + 1;
    var yOf = yScale(min, max, pad.top, plotH);
    var ticks = 4;
    for (var t = 0; t <= ticks; t += 1) {
      var value = min + ((max - min) * t) / ticks;
      var y = yOf(value);
      svg.appendChild(svgEl("line", {
        x1: pad.left,
        x2: pad.left + plotW,
        y1: y,
        y2: y,
        stroke: "var(--line)",
      }));
      svg.appendChild(svgText({
        x: pad.left - 6,
        y: y + 4,
        "text-anchor": "end",
        fill: "var(--muted)",
        "font-size": "11",
      }, formatTick(value)));
    }
    svg.appendChild(svgEl("line", {
      x1: pad.left,
      y1: pad.top,
      x2: pad.left,
      y2: pad.top + plotH,
      stroke: "var(--ink)",
    }));
    svg.appendChild(svgEl("line", {
      x1: pad.left,
      y1: pad.top + plotH,
      x2: pad.left + plotW,
      y2: pad.top + plotH,
      stroke: "var(--ink)",
    }));

    var n = spec.labels.length;
    var groupW = n ? plotW / n : plotW;
    var zero = yOf(0);
    if (spec.type === "line") {
      spec.series.forEach(function (row, si) {
        var color = SERIES_COLORS[si % SERIES_COLORS.length];
        var points = row.values.map(function (value, i) {
          return (pad.left + groupW * (i + 0.5)) + "," + yOf(value);
        }).join(" ");
        svg.appendChild(svgEl("polyline", {
          points: points,
          fill: "none",
          stroke: color,
          "stroke-width": 2,
        }));
        row.values.forEach(function (value, i) {
          svg.appendChild(svgEl("circle", {
            cx: pad.left + groupW * (i + 0.5),
            cy: yOf(value),
            r: 3,
            fill: color,
          }));
        });
      });
    } else {
      var inner = groupW * 0.72;
      var barW = Math.max(inner / spec.series.length, 1);
      spec.series.forEach(function (row, si) {
        var color = SERIES_COLORS[si % SERIES_COLORS.length];
        row.values.forEach(function (value, i) {
          var x = pad.left + groupW * i + (groupW - inner) / 2 + barW * si;
          var y = yOf(Math.max(value, 0));
          var yBase = value >= 0 ? zero : yOf(value);
          var heightBar = Math.max(Math.abs((value >= 0 ? zero : yOf(0)) - yOf(value)), 1);
          svg.appendChild(svgEl("rect", {
            x: x,
            y: value >= 0 ? y : yBase,
            width: Math.max(barW - 2, 1),
            height: heightBar,
            fill: color,
          }));
        });
      });
    }

    spec.labels.forEach(function (label, i) {
      svg.appendChild(svgText({
        x: pad.left + groupW * (i + 0.5),
        y: pad.top + plotH + 18,
        "text-anchor": "middle",
        fill: "var(--muted)",
        "font-size": "11",
      }, truncateLabel(label, 12)));
    });
    return svg;
  }

  function polar(cx, cy, radius, angle) {
    return {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  }

  function drawPieChart(spec) {
    var width = 560;
    var height = 300;
    var cx = 170;
    var cy = 160;
    var radius = 96;
    var svg = svgEl("svg", {
      class: "chat-chart",
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": spec.title || "pie chart",
    });
    svg.appendChild(svgEl("rect", {
      width: width,
      height: height,
      fill: "var(--card)",
      rx: 8,
    }));
    if (spec.title) {
      svg.appendChild(svgText({
        x: width / 2,
        y: 22,
        "text-anchor": "middle",
        fill: "var(--ink)",
        "font-size": "14",
        "font-weight": "650",
      }, spec.title));
    }
    var row = spec.series[0];
    var slices = row.values.map(function (value) {
      return Math.max(Number(value) || 0, 0);
    });
    var total = slices.reduce(function (sum, value) { return sum + value; }, 0);
    if (total <= 0) {
      svg.appendChild(svgEl("circle", {
        cx: cx,
        cy: cy,
        r: radius,
        fill: "none",
        stroke: "var(--line)",
      }));
      svg.appendChild(svgText({
        x: cx,
        y: cy + 4,
        "text-anchor": "middle",
        fill: "var(--muted)",
        "font-size": "12",
      }, "No values"));
      return svg;
    }

    var angle = -Math.PI / 2;
    slices.forEach(function (slice, i) {
      var sweep = (slice / total) * Math.PI * 2;
      var color = SERIES_COLORS[i % SERIES_COLORS.length];
      if (slice <= 0) return;
      if (Math.abs(sweep - Math.PI * 2) < 1e-9) {
        svg.appendChild(svgEl("circle", { cx: cx, cy: cy, r: radius, fill: color }));
      } else {
        var start = polar(cx, cy, radius, angle);
        var end = polar(cx, cy, radius, angle + sweep);
        var large = sweep > Math.PI ? 1 : 0;
        var d = "M " + cx + " " + cy
          + " L " + start.x + " " + start.y
          + " A " + radius + " " + radius + " 0 " + large + " 1 " + end.x + " " + end.y
          + " Z";
        svg.appendChild(svgEl("path", { d: d, fill: color }));
      }
      angle += sweep;
    });

    spec.labels.forEach(function (label, i) {
      var y = 56 + i * 22;
      svg.appendChild(svgEl("rect", {
        x: 320,
        y: y - 9,
        width: 10,
        height: 10,
        fill: SERIES_COLORS[i % SERIES_COLORS.length],
      }));
      svg.appendChild(svgText({
        x: 336,
        y: y,
        fill: "var(--ink)",
        "font-size": "12",
      }, truncateLabel(label, 22) + "  " + formatTick(row.values[i])));
    });
    return svg;
  }

  function drawChartSvg(spec) {
    if (!spec) return null;
    if (spec.type === "pie") return drawPieChart(spec);
    return drawAxisChart(spec);
  }

  function figureHasRound(spec) {
    return (spec.elements || []).some(function (el) {
      return el.kind === "circle" || el.kind === "arc" || el.kind === "sector";
    });
  }

  function geometryBox(spec) {
    var xs = [];
    var ys = [];
    (spec.elements || []).forEach(function (el) {
      if (el.kind === "circle" || el.kind === "arc" || el.kind === "sector") {
        xs.push(el.cx - el.r, el.cx + el.r);
        ys.push(el.cy - el.r, el.cy + el.r);
      } else if (el.kind === "point" || el.kind === "label") {
        xs.push(el.x);
        ys.push(el.y);
      } else if (el.kind === "segment" || el.kind === "arrow") {
        xs.push(el.from[0], el.to[0]);
        ys.push(el.from[1], el.to[1]);
      } else if (el.kind === "polygon") {
        el.points.forEach(function (pt) { xs.push(pt[0]); ys.push(pt[1]); });
      } else if (el.kind === "angle") {
        xs.push(el.at[0], el.from[0], el.to[0]);
        ys.push(el.at[1], el.from[1], el.to[1]);
      }
    });
    if (!xs.length || !ys.length) {
      return { xmin: 0, xmax: 100, ymin: 0, ymax: 100 };
    }
    var xmin = Math.min.apply(null, xs);
    var xmax = Math.max.apply(null, xs);
    var ymin = Math.min.apply(null, ys);
    var ymax = Math.max.apply(null, ys);
    if (xmin === xmax) xmax = xmin + 1;
    if (ymin === ymax) ymax = ymin + 1;
    var padFrac = figureHasRound(spec) ? 0.16 : 0.1;
    var padX = Math.max((xmax - xmin) * padFrac, figureHasRound(spec) ? 8 : 4);
    var padY = Math.max((ymax - ymin) * padFrac, figureHasRound(spec) ? 8 : 4);
    return {
      xmin: xmin - padX,
      xmax: xmax + padX,
      ymin: ymin - padY,
      ymax: ymax + padY,
    };
  }

  function mapBounds(spec, width, height, pad) {
    var yUp = spec.type === "coordinate";
    var xmin = 0;
    var xmax = 100;
    var ymin = 0;
    var ymax = 100;
    if (spec.axes) {
      xmin = spec.axes.xmin;
      xmax = spec.axes.xmax;
      ymin = spec.axes.ymin;
      ymax = spec.axes.ymax;
    } else if (spec.type === "coordinate") {
      var box = geometryBox(spec);
      xmin = box.xmin;
      xmax = box.xmax;
      ymin = box.ymin;
      ymax = box.ymax;
    } else {
      var geo = geometryBox(spec);
      xmin = geo.xmin;
      xmax = geo.xmax;
      ymin = geo.ymin;
      ymax = geo.ymax;
    }
    var innerW = width - pad.left - pad.right;
    var innerH = height - pad.top - pad.bottom;
    var xRange = xmax - xmin || 1;
    var yRange = ymax - ymin || 1;
    var left = pad.left;
    var top = pad.top;
    var usedW = innerW;
    var usedH = innerH;
    if (!yUp) {
      var scale = Math.min(innerW / xRange, innerH / yRange);
      usedW = xRange * scale;
      usedH = yRange * scale;
      left = pad.left + (innerW - usedW) / 2;
      top = pad.top + (innerH - usedH) / 2;
    }
    return {
      xmin: xmin,
      xmax: xmax,
      ymin: ymin,
      ymax: ymax,
      left: left,
      top: top,
      width: usedW,
      height: usedH,
      yUp: yUp,
    };
  }

  function mapPointToPx(point, bounds) {
    var xRange = bounds.xmax - bounds.xmin || 1;
    var yRange = bounds.ymax - bounds.ymin || 1;
    var x = bounds.left + ((point[0] - bounds.xmin) / xRange) * bounds.width;
    var y;
    if (bounds.yUp) {
      y = bounds.top + bounds.height - ((point[1] - bounds.ymin) / yRange) * bounds.height;
    } else {
      y = bounds.top + ((point[1] - bounds.ymin) / yRange) * bounds.height;
    }
    return { x: x, y: y };
  }

  function unitVec(from, to) {
    var dx = to.x - from.x;
    var dy = to.y - from.y;
    var len = Math.hypot(dx, dy) || 1;
    return { x: dx / len, y: dy / len };
  }

  function offsetPoint(a, b, amount) {
    var n = unitVec(a, b);
    return { x: (a.x + b.x) / 2 + -n.y * amount, y: (a.y + b.y) / 2 + n.x * amount };
  }

  function polarPx(centre, radius, deg) {
    var rad = (Number(deg) * Math.PI) / 180;
    return { x: centre.x + radius * Math.cos(rad), y: centre.y + radius * Math.sin(rad) };
  }

  function markHit(node, el) {
    if (!node || !el || !el.id) return node;
    node.setAttribute("data-part", el.id);
    node.classList.add("chat-figure-hit");
    if (el.match) node.setAttribute("data-match", el.match);
    if (el.caption) node.setAttribute("data-caption", el.caption);
    return node;
  }

  function drawNumberLine(spec) {
    var width = 560;
    var height = spec.title ? 140 : 110;
    var pad = { left: 36, right: 36, top: spec.title ? 40 : 28, bottom: 36 };
    var svg = svgEl("svg", {
      class: "chat-chart chat-figure-svg",
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": spec.title || spec.caption || "number line",
    });
    svg.appendChild(svgEl("rect", { width: width, height: height, fill: "var(--card)", rx: 8 }));
    if (spec.title) {
      svg.appendChild(svgText({
        x: width / 2, y: 22, "text-anchor": "middle", fill: "var(--ink)",
        "font-size": "14", "font-weight": "650",
      }, spec.title));
    }
    var y = pad.top + 28;
    var x0 = pad.left;
    var x1 = width - pad.right;
    svg.appendChild(svgEl("line", { x1: x0, y1: y, x2: x1, y2: y, stroke: "var(--ink)", "stroke-width": "2" }));
    svg.appendChild(svgEl("polygon", {
      points: (x1) + "," + y + " " + (x1 - 8) + "," + (y - 5) + " " + (x1 - 8) + "," + (y + 5),
      fill: "var(--ink)",
    }));
    function xOf(value) {
      return x0 + ((value - spec.min) / (spec.max - spec.min || 1)) * (x1 - x0 - 10);
    }
    var marks = spec.marks && spec.marks.length ? spec.marks : [spec.min, spec.max];
    marks.forEach(function (mark) {
      var x = xOf(mark);
      svg.appendChild(svgEl("line", { x1: x, y1: y - 8, x2: x, y2: y + 8, stroke: "var(--ink)" }));
      svg.appendChild(svgText({
        x: x, y: y + 22, "text-anchor": "middle", fill: "var(--muted)", "font-size": "11",
      }, formatTick(mark)));
    });
    (spec.points || []).forEach(function (row) {
      var x = xOf(row.value);
      svg.appendChild(svgEl("circle", { cx: x, cy: y, r: 5, fill: "var(--green)" }));
      if (row.label) {
        svg.appendChild(svgText({
          x: x, y: y - 12, "text-anchor": "middle", fill: "var(--ink)", "font-size": "12",
        }, row.label));
      }
    });
    return svg;
  }

  function drawGeometryFigure(spec) {
    var width = 560;
    var pad = { top: spec.title ? 48 : 28, right: 32, bottom: 32, left: 32 };
    var box = geometryBox(spec);
    var xRange = box.xmax - box.xmin || 1;
    var yRange = box.ymax - box.ymin || 1;
    var innerW = width - pad.left - pad.right;
    var innerH = innerW * (yRange / xRange);
    if (figureHasRound(spec)) innerH = Math.max(innerH, innerW);
    innerH = Math.max(240, Math.min(520, innerH));
    var height = Math.round(innerH + pad.top + pad.bottom);
    var bounds = mapBounds(spec, width, height, pad);
    var svg = svgEl("svg", {
      class: "chat-chart chat-figure-svg",
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      overflow: "visible",
      "aria-label": spec.title || spec.caption || spec.type + " figure",
    });
    svg.appendChild(svgEl("rect", { width: width, height: height, fill: "var(--card)", rx: 8 }));
    if (spec.title) {
      svg.appendChild(svgText({
        x: width / 2, y: 22, "text-anchor": "middle", fill: "var(--ink)",
        "font-size": "14", "font-weight": "650",
      }, spec.title));
    }
    if (spec.type === "coordinate") {
      var origin = mapPointToPx([0, 0], bounds);
      var left = mapPointToPx([bounds.xmin, 0], bounds);
      var right = mapPointToPx([bounds.xmax, 0], bounds);
      var bottom = mapPointToPx([0, bounds.ymin], bounds);
      var top = mapPointToPx([0, bounds.ymax], bounds);
      svg.appendChild(svgEl("line", {
        x1: left.x, y1: origin.y, x2: right.x, y2: origin.y,
        stroke: "var(--ink)", "stroke-width": "1.5",
      }));
      svg.appendChild(svgEl("line", {
        x1: origin.x, y1: bottom.y, x2: origin.x, y2: top.y,
        stroke: "var(--ink)", "stroke-width": "1.5",
      }));
    }
    function placeLabel(pt, text, dx, dy) {
      if (!text) return;
      svg.appendChild(svgText({
        x: pt.x + (dx || 6),
        y: pt.y + (dy || -6),
        fill: "var(--ink)",
        "font-size": "12",
      }, text));
    }
    (spec.elements || []).forEach(function (el) {
      if (el.kind === "polygon") {
        var mapped = el.points.map(function (pt) { return mapPointToPx(pt, bounds); });
        var pts = mapped.map(function (pt) { return pt.x + "," + pt.y; }).join(" ");
        svg.appendChild(markHit(svgEl("polygon", {
          points: pts,
          fill: el.fill ? "var(--green-bg)" : "none",
          stroke: "var(--ink)",
          "stroke-width": "2",
        }), el));
        mapped.forEach(function (pt, index) {
          placeLabel(pt, el.labels && el.labels[index], 6, -6);
        });
      } else if (el.kind === "segment" || el.kind === "arrow") {
        var a = mapPointToPx(el.from, bounds);
        var b = mapPointToPx(el.to, bounds);
        if (el.id) {
          svg.appendChild(markHit(svgEl("line", {
            x1: a.x, y1: a.y, x2: b.x, y2: b.y,
            stroke: "transparent", "stroke-width": "14",
          }), el));
        }
        svg.appendChild(markHit(svgEl("line", {
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          stroke: "var(--ink)", "stroke-width": "2",
        }), el));
        if (el.kind === "arrow") {
          var dir = unitVec(a, b);
          var leftA = { x: b.x - dir.x * 10 + -dir.y * 5, y: b.y - dir.y * 10 + dir.x * 5 };
          var rightA = { x: b.x - dir.x * 10 - -dir.y * 5, y: b.y - dir.y * 10 - dir.x * 5 };
          svg.appendChild(svgEl("polygon", {
            points: b.x + "," + b.y + " " + leftA.x + "," + leftA.y + " " + rightA.x + "," + rightA.y,
            fill: "var(--ink)",
          }));
        }
        if (el.label) {
          var mid = offsetPoint(a, b, 10);
          svg.appendChild(svgText({
            x: mid.x, y: mid.y, "text-anchor": "middle", fill: "var(--ink)", "font-size": "12",
          }, el.label));
        }
      } else if (el.kind === "circle") {
        var c = mapPointToPx([el.cx, el.cy], bounds);
        var rimX = mapPointToPx([el.cx + el.r, el.cy], bounds);
        var rimY = mapPointToPx([el.cx, el.cy + el.r], bounds);
        var rpx = Math.min(Math.abs(rimX.x - c.x), Math.abs(rimY.y - c.y));
        svg.appendChild(markHit(svgEl("circle", {
          cx: c.x, cy: c.y, r: Math.max(4, rpx),
          fill: "none", stroke: "var(--ink)", "stroke-width": "2",
        }), el));
        placeLabel(c, el.label, 8, -8);
      } else if (el.kind === "sector" || el.kind === "arc") {
        var sc = mapPointToPx([el.cx, el.cy], bounds);
        var srpx = Math.min(
          Math.abs(mapPointToPx([el.cx + el.r, el.cy], bounds).x - sc.x),
          Math.abs(mapPointToPx([el.cx, el.cy + el.r], bounds).y - sc.y)
        );
        srpx = Math.max(4, srpx);
        var sStart = polarPx(sc, srpx, el.start);
        var sEnd = polarPx(sc, srpx, el.end);
        var delta = ((Number(el.end) - Number(el.start)) % 360 + 360) % 360;
        var large = delta > 180 ? 1 : 0;
        if (el.kind === "sector") {
          svg.appendChild(markHit(svgEl("path", {
            d: "M " + sc.x + " " + sc.y + " L " + sStart.x + " " + sStart.y
              + " A " + srpx + " " + srpx + " 0 " + large + " 1 " + sEnd.x + " " + sEnd.y + " Z",
            fill: el.fill !== false ? "var(--green-bg)" : "none",
            stroke: "var(--ink)",
            "stroke-width": "2",
          }), el));
        } else {
          svg.appendChild(markHit(svgEl("path", {
            d: "M " + sStart.x + " " + sStart.y + " A " + srpx + " " + srpx + " 0 " + large
              + " 1 " + sEnd.x + " " + sEnd.y,
            fill: "none",
            stroke: "var(--green)",
            "stroke-width": "4",
          }), el));
        }
        if (el.label) placeLabel(sc, el.label, 8, -8);
      } else if (el.kind === "point") {
        var p = mapPointToPx([el.x, el.y], bounds);
        svg.appendChild(markHit(svgEl("circle", { cx: p.x, cy: p.y, r: 6, fill: "var(--ink)" }), el));
        placeLabel(p, el.label, 8, -8);
      } else if (el.kind === "label") {
        placeLabel(mapPointToPx([el.x, el.y], bounds), el.text, 0, 0);
      } else if (el.kind === "angle") {
        var vertex = mapPointToPx(el.at, bounds);
        var fromPt = mapPointToPx(el.from, bounds);
        var toPt = mapPointToPx(el.to, bounds);
        var u = unitVec(vertex, fromPt);
        var v = unitVec(vertex, toPt);
        if (el.right) {
          var s = 12;
          var p1 = { x: vertex.x + u.x * s, y: vertex.y + u.y * s };
          var p3 = { x: vertex.x + v.x * s, y: vertex.y + v.y * s };
          var p2 = { x: p1.x + v.x * s, y: p1.y + v.y * s };
          svg.appendChild(markHit(svgEl("polyline", {
            points: p1.x + "," + p1.y + " " + p2.x + "," + p2.y + " " + p3.x + "," + p3.y,
            fill: "none", stroke: "var(--ink)", "stroke-width": "1.5",
          }), el));
        } else {
          var radius = 18;
          var a1 = Math.atan2(u.y, u.x);
          var a2 = Math.atan2(v.y, v.x);
          var sweep = a2 - a1;
          if (sweep > Math.PI) sweep -= 2 * Math.PI;
          if (sweep < -Math.PI) sweep += 2 * Math.PI;
          var end = { x: vertex.x + Math.cos(a1 + sweep) * radius, y: vertex.y + Math.sin(a1 + sweep) * radius };
          var start = { x: vertex.x + Math.cos(a1) * radius, y: vertex.y + Math.sin(a1) * radius };
          svg.appendChild(markHit(svgEl("path", {
            d: "M " + start.x + " " + start.y + " A " + radius + " " + radius + " 0 0 "
              + (sweep > 0 ? "1" : "0") + " " + end.x + " " + end.y,
            fill: "none",
            stroke: "var(--ink)",
            "stroke-width": "1.5",
          }), el));
        }
        if (el.label) {
          var bis = { x: u.x + v.x, y: u.y + v.y };
          var bl = Math.hypot(bis.x, bis.y) || 1;
          svg.appendChild(svgText({
            x: vertex.x + (bis.x / bl) * 28,
            y: vertex.y + (bis.y / bl) * 28,
            "text-anchor": "middle",
            fill: "var(--ink)",
            "font-size": "12",
          }, el.label));
        }
      }
    });
    return svg;
  }

  function wrapFigure(svg, spec) {
    if (!svg) return null;
    var caption = spec && spec.caption ? spec.caption : "";
    var figure = document.createElement("figure");
    figure.className = "chat-figure";
    figure.appendChild(svg);
    var cap = document.createElement("figcaption");
    cap.textContent = caption || (spec && spec.hint) || "Click a part of the diagram.";
    figure.appendChild(cap);
    return attachFigureInteractivity(figure, spec || {});
  }

  function attachFigureInteractivity(figureEl, spec) {
    var hits = figureEl.querySelectorAll("[data-part]");
    var actions = spec.actions || [];
    if (!hits.length && !actions.length) return figureEl;
    figureEl.classList.add("chat-figure-interactive");
    var cap = figureEl.querySelector("figcaption");
    function highlight(ids) {
      var wanted = {};
      (ids || []).forEach(function (id) { wanted[id] = true; });
      figureEl.querySelectorAll("[data-part]").forEach(function (node) {
        var id = node.getAttribute("data-part");
        var match = node.getAttribute("data-match");
        var on = !!(wanted[id] || (match && wanted[match]));
        node.classList.toggle("is-active", on);
      });
    }
    figureEl.addEventListener("click", function (event) {
      var hit = event.target.closest("[data-part]");
      if (!hit || !figureEl.contains(hit)) return;
      var id = hit.getAttribute("data-part");
      var match = hit.getAttribute("data-match");
      var ids = [id];
      if (match) ids.push(match);
      highlight(ids);
      if (cap) {
        cap.textContent = hit.getAttribute("data-caption") || ("Selected " + id + ".");
      }
    });
    if (actions.length) {
      var bar = document.createElement("div");
      bar.className = "chat-figure-actions";
      actions.forEach(function (action) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "secondary";
        btn.textContent = action.label;
        btn.addEventListener("click", function () {
          highlight(action.highlight || []);
          if (cap) cap.textContent = action.caption || action.label;
          bar.querySelectorAll("button").forEach(function (node) {
            node.removeAttribute("aria-pressed");
          });
          btn.setAttribute("aria-pressed", "true");
        });
        bar.appendChild(btn);
      });
      if (cap && cap.parentNode) cap.parentNode.insertBefore(bar, cap);
      else figureEl.appendChild(bar);
    }
    return figureEl;
  }

  function drawFigureSvg(spec) {
    if (!spec) return null;
    if (spec.type === "chart" || spec.type === "bar" || spec.type === "line" || spec.type === "pie") {
      return wrapFigure(drawChartSvg(spec), spec);
    }
    if (spec.type === "number_line") return wrapFigure(drawNumberLine(spec), spec);
    return wrapFigure(drawGeometryFigure(spec), spec);
  }

  function fallbackPre(text) {
    var pre = document.createElement("pre");
    pre.className = "chat-chart-fallback";
    pre.textContent = text == null ? "" : String(text);
    return pre;
  }

  function isFenceLine(line) {
    return /^```/.test(String(line || ""));
  }

  function isBlockStart(lines, index) {
    var line = lines[index];
    if (!line || !line.trim()) return true;
    if (HEADING_RE.test(line) || UL_RE.test(line) || OL_RE.test(line) || isFenceLine(line)) return true;
    if (looksLikeTableRow(line) && index + 1 < lines.length && isTableSeparator(lines[index + 1])) return true;
    return false;
  }

  function appendMarkdownBlocks(parent, text) {
    var lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];
      if (!line.trim()) {
        i += 1;
        continue;
      }

      var heading = HEADING_RE.exec(line);
      if (heading) {
        var headingEl = document.createElement("h" + heading[1].length);
        appendInline(headingEl, heading[2]);
        parent.appendChild(headingEl);
        i += 1;
        continue;
      }

      if (looksLikeTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        var tableLines = [line, lines[i + 1]];
        i += 2;
        while (i < lines.length && looksLikeTableRow(lines[i])) {
          tableLines.push(lines[i]);
          i += 1;
        }
        var table = markdownTableToHtml(tableLines.join("\n"));
        if (table) parent.appendChild(table);
        continue;
      }

      if (UL_RE.test(line)) {
        var ul = document.createElement("ul");
        while (i < lines.length && UL_RE.test(lines[i])) {
          var ulItem = document.createElement("li");
          appendInline(ulItem, UL_RE.exec(lines[i])[1]);
          ul.appendChild(ulItem);
          i += 1;
        }
        parent.appendChild(ul);
        continue;
      }

      if (OL_RE.test(line)) {
        var ol = document.createElement("ol");
        while (i < lines.length && OL_RE.test(lines[i])) {
          var olItem = document.createElement("li");
          appendInline(olItem, OL_RE.exec(lines[i])[1]);
          ol.appendChild(olItem);
          i += 1;
        }
        parent.appendChild(ol);
        continue;
      }

      if (isFenceLine(line)) {
        var fence = [];
        i += 1;
        while (i < lines.length && !isFenceLine(lines[i])) {
          fence.push(lines[i]);
          i += 1;
        }
        if (i < lines.length) i += 1;
        parent.appendChild(fallbackPre(fence.join("\n")));
        continue;
      }

      var para = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines, i)) {
        para.push(lines[i]);
        i += 1;
      }
      if (!para.length) {
        para.push(line);
        i += 1;
      }
      var p = document.createElement("p");
      appendInline(p, para.join(" "));
      parent.appendChild(p);
    }
  }

  function renderAssistantReply(text) {
    var container = document.createElement("div");
    container.className = "chat-reply";
    var parts = splitMediaFences(text);
    if (!parts.length) {
      appendMarkdownBlocks(container, "");
      return container;
    }
    for (var i = 0; i < parts.length; i += 1) {
      var part = parts[i];
      if (part.kind === "chart") {
        var spec = parseChartFence(part.text);
        var chart = spec ? drawChartSvg(spec) : null;
        container.appendChild(chart || fallbackPre(part.raw || part.text));
      } else if (part.kind === "figure") {
        var figureSpec = parseFigureSpec(part.text);
        var drawn = figureSpec ? drawFigureSvg(figureSpec) : null;
        container.appendChild(drawn || fallbackPre(part.raw || part.text));
      } else {
        appendMarkdownBlocks(container, part.text);
      }
    }
    return container;
  }

  global.escapeHtml = escapeHtml;
  global.parseChartFence = parseChartFence;
  global.parseFigureSpec = parseFigureSpec;
  global.markdownTableToHtml = markdownTableToHtml;
  global.renderAssistantReply = renderAssistantReply;
  global.drawChartSvg = drawChartSvg;
  global.drawFigureSvg = drawFigureSvg;
})(typeof window !== "undefined" ? window : this);
