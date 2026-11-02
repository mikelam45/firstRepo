export function recognitionLanguage(target, accent) {
  if (target === "cmn") return "zh-CN";
  if (target === "yue") return "zh-HK";
  return accent === "en-US" ? "en-US" : "en-GB";
}

export function transcriptPiece(results, index) {
  const row = rowAt(results, index);
  const alt = rowAt(row, 0);
  const transcript = alt && alt.transcript;
  return typeof transcript === "string" ? transcript : "";
}

export function collectTranscript(results) {
  if (!results || typeof results.length !== "number") return "";
  let text = "";
  for (let i = 0; i < results.length; i += 1) {
    text += transcriptPiece(results, i);
  }
  return text.trim();
}

function rowAt(list, index) {
  if (!list || typeof index !== "number") return null;
  if (list[index] != null) return list[index];
  if (typeof list.item !== "function") return null;
  try {
    return list.item(index);
  } catch (err) {
    return null;
  }
}
