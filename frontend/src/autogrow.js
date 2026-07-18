// Resizes a textarea-like element (anything with .style and .scrollHeight) to fit
// its current content. Reset to "auto" first so scrollHeight reflects a SHRINK too
// (deleting text), not just growth — otherwise the box would only ever get taller.
export function autoGrowTextarea(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}
