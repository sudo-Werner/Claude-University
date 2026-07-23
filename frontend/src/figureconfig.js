// Animated-figure client DOMPurify config (defense in depth over
// backend/figures.py's allow_animation sanitizer). Its own module so the
// client-layer sanitizer harness can import the exact config the app uses.
// Adds only the animateTransform/animateMotion subset to the advisory
// allowlists; the FORBID lists are operative and kill the dangerous animation
// elements and href even if a future DOMPurify default promotes them.
export const SVG_ANIM_SANITIZE_CONFIG = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ALLOWED_TAGS: ["svg","g","rect","circle","ellipse","line","polyline","polygon","path","text","tspan","title","defs","marker","animateTransform","animateMotion"],
  ALLOWED_ATTR: ["viewBox","x","y","x1","y1","x2","y2","cx","cy","r","rx","ry","width","height","d","points","transform","fill","stroke","stroke-width","stroke-dasharray","stroke-linecap","stroke-linejoin","font-size","font-family","font-weight","text-anchor","dominant-baseline","opacity","fill-opacity","marker-end","marker-start","id","class","attributeName","type","dur","begin","repeatCount","values","additive","accumulate","path","keyPoints","rotate"],
  FORBID_TAGS: ["animate","set","mpath","animateColor","discard","style","image","use","a","foreignObject","script"],
  FORBID_ATTR: ["href","xlink:href"],
};
