/* Functions-page assistant reply formatter. Builds DOM nodes from a safe subset. */
(function (global) {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var SERIES_COLORS = ["var(--green)", "var(--amber)", "var(--rust)", "var(--ink)", "var(--muted)"];
  var CHART_FENCE_RE = /```chart[^\n]*\n([\s\S]*?)```/g;
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
    };
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

  function splitChartFences(text) {
    var src = String(text || "");
    var parts = [];
    var last = 0;
    var match;
    CHART_FENCE_RE.lastIndex = 0;
    while ((match = CHART_FENCE_RE.exec(src))) {
      if (match.index > last) {
        parts.push({ kind: "md", text: src.slice(last, match.index) });
      }
      parts.push({ kind: "chart", text: match[1], raw: match[0] });
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
    var parts = splitChartFences(text);
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
      } else {
        appendMarkdownBlocks(container, part.text);
      }
    }
    return container;
  }

  global.escapeHtml = escapeHtml;
  global.parseChartFence = parseChartFence;
  global.markdownTableToHtml = markdownTableToHtml;
  global.renderAssistantReply = renderAssistantReply;
  global.drawChartSvg = drawChartSvg;
})(typeof window !== "undefined" ? window : this);
