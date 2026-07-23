// Brand mermaid theme, prepended at render time so it also re-themes figures
// already cached on disk (no backfill needed). Maps mermaid's base theme to the
// design tokens (content/design/tokens.md): brand purple nodes on a transparent
// ground so the glass card shows through. Safe under securityLevel:"strict"
// (themeVariables is not in mermaid's secure lock-list).
export const MERMAID_INIT =
  '%%{init: {"theme":"base","themeVariables":{' +
  '"primaryColor":"#ece7ff","primaryBorderColor":"#7c6aff","primaryTextColor":"#241f1a",' +
  '"lineColor":"#7c6aff","secondaryColor":"#e8f2fb","tertiaryColor":"#fbf7ee",' +
  '"fontFamily":"system-ui, -apple-system, Segoe UI, Roboto, sans-serif",' +
  '"background":"transparent"}}}%%\n';

export function themedMermaid(code) {
  const src = typeof code === "string" ? code : "";
  if (src.trimStart().startsWith("%%{init")) return src; // already themed
  return MERMAID_INIT + src;
}
