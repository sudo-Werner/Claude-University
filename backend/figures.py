"""Strict allowlist SVG sanitizer for Claude-authored diagrams — server side, run once
at generation time before a lesson is cached. Never repairs: any forbidden element,
forbidden attribute, missing viewBox, a width/height on the root, or unparseable XML
means the WHOLE figure is dropped (returns None), never a partially-cleaned figure.
Client-side DOMPurify is a second, independent layer at render time (spec decision 3) —
this function is not the only defense, but it must never let anything hostile through
on its own.
"""

import re
import xml.etree.ElementTree as ET

MAX_INPUT_BYTES = 8 * 1024

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"

ALLOWED_ELEMENTS = {
    "svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "path", "text", "tspan", "title", "defs", "marker",
}

ALLOWED_ATTRS = {
    "viewBox", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "d", "points", "transform", "fill", "stroke",
    "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "font-size", "font-family",
    "font-weight", "text-anchor", "dominant-baseline", "opacity",
    "fill-opacity", "marker-end", "marker-start", "id", "class",
}

ANIM_ELEMENTS = {"animateTransform", "animateMotion"}
ANIM_ATTRS = {
    "attributeName", "type", "dur", "begin", "repeatCount", "values",
    "additive", "accumulate", "path", "keyPoints", "rotate",
}
_TRANSFORM_TYPES = {"translate", "scale", "rotate", "skewX", "skewY"}
_MAX_DRAWN_ELEMENTS = 30
_MAX_ANIM_ELEMENTS = 8
_CLOCK_RE = re.compile(r"^(-?\d+(?:\.\d+)?)(s|ms)?$")
_NUMLIST_RE = re.compile(r"^[\s\d.,;+\-eE]+$")
_PATH_RE = re.compile(r"^[\sMmLlHhVvCcSsQqTtAaZz0-9.,\-eE]+$")
_POSNUM_RE = re.compile(r"^\d+(?:\.\d+)?$")

# Prompt copy shared by generation.py's _IMAGES_BLOCK and images.py's backfill_prompt —
# lives here (not in generation.py or images.py) so neither of those two modules needs
# to import the other just for this string (images.py already needs sanitize_svg above;
# generation.py already imports images.py — putting this text in either of THEM would
# risk a circular import).
DRAWN_FIGURE_GUIDANCE = (
    "\n\nChoose the figure TYPE by what the content needs (this is independent of "
    "how hard the content is):\n"
    "  - web-image (a real photo/plate) whenever the learner must recognize a real "
    "thing by appearance — anatomy, organisms, minerals, artefacts. A drawing cannot "
    "substitute; this is first-class, never a fallback.\n"
    "  - a static drawn diagram (mermaid for a process/flow/hierarchy/timeline or "
    "quantitative chart; svg for a labelled spatial schematic mermaid cannot express, "
    "keep it simple: at most ~25 elements) when structure or relationships are the "
    "point and a still with arrows and labels reads at a glance.\n"
    "  - svg-animated ONLY when the meaning IS change over time (a flow, a cycle, a "
    "process in motion) and a static frame would genuinely lose the point.\n"
    '  A mermaid slot: {"type": "mermaid", "code": "<mermaid source>", "caption": '
    '"<one sentence saying what to NOTICE>"}.\n'
    '  An svg slot: {"type": "svg", "code": "<svg ...>...</svg>", "caption": "<one '
    'sentence saying what to NOTICE>"}. SVG style contract (stay inside the sanitizer '
    'allowlist): fixed viewBox="0 0 800 500"; NO gradients, NO filter/blur/shadow, NO '
    '<style> (all banned) — use flat fill plus fill-opacity tints for depth; draw '
    'arrowheads as <polygon> triangles (marker sizing attrs are not allowed); label '
    'every part with a <text> element (font-size at least 14px) ON the drawing, never a '
    'separate legend. Use the brand palette — ink #241f1a for labels/strokes, purple '
    '#7c6aff and its soft tint for structure — EXCEPT where a colour itself carries the '
    'meaning (arterial-red vs venous-blue, hot vs cold, acid vs base): there use the '
    'established domain convention, not the brand colour.\n'
    '  An svg-animated slot: {"type": "svg-animated", "code": "<svg ...>...</svg>", '
    '"caption": "<one sentence saying what to NOTICE>"}. Use ONLY when the meaning IS '
    "change over time (a flow, cycle, or process in motion) — a static frame with arrows "
    "cannot carry it. Hard rules: the drawing must be a correct, fully-labelled diagram "
    "with the animation REMOVED — base positions equal the start state and motion is "
    "expressed relatively (paths from M0,0), so stripping the animation leaves a sensible "
    "still. Prefer animateMotion (a <circle> travelling a path). Allowed animation is "
    "animateTransform (attributeName=\"transform\", type translate/scale/rotate/skewX/skewY) "
    "and animateMotion only; no other animation elements, no <style>, no href. Keep it "
    "under 30 drawn and 8 animation elements, each dur 1-20s; at most ONE animated figure "
    "per lesson. Labels stay fixed. Colours from the brand palette, except where a colour "
    "carries meaning (arterial-red vs venous-blue).\n"
    '  A web-image slot may also state "type": "web-image" explicitly (omitting type '
    "still defaults to web-image).\n"
)


def valid_image_slot(slot):
    """Per-slot shape check shared by generation.valid_images and
    images._valid_images_slots (single source of truth). web-image (or no type):
    non-empty query + caption. mermaid/svg: non-empty code (<=8192 chars) +
    caption. Any other type is invalid."""
    if not isinstance(slot, dict):
        return False
    kind = slot.get("type", "web-image")
    if kind == "web-image":
        return all(isinstance(slot.get(f), str) and slot[f].strip() for f in ("query", "caption"))
    if kind in ("mermaid", "svg", "svg-animated"):
        code = slot.get("code")
        if not (isinstance(code, str) and code.strip() and len(code) <= 8192):
            return False
        return isinstance(slot.get("caption"), str) and bool(slot["caption"].strip())
    return False


def _local_name(tag):
    """Strip a Clark-notation namespace (e.g. '{http://www.w3.org/2000/svg}rect' ->
    ('rect', 'http://www.w3.org/2000/svg')) so the allowlist check is namespace-aware
    but not namespace-syntax-dependent. Returns (local_name, namespace_uri_or_None)."""
    if tag.startswith("{"):
        uri, _, local = tag[1:].partition("}")
        return local, uri
    return tag, None


def _clock_seconds(value):
    """Parse an SMIL clock-value ('2s', '500ms', '1.5', '-0.5s') to float seconds,
    or None if it is not a bare clock-value (rejects all event syntax)."""
    m = _CLOCK_RE.match(value.strip())
    if not m:
        return None
    num = float(m.group(1))
    return num / 1000.0 if m.group(2) == "ms" else num


def _valid_anim_attr(el_local, name, value):
    """Value-restrict one animation attribute. Returns False -> whole figure dropped."""
    if name == "attributeName":
        return el_local == "animateTransform" and value == "transform"
    if name == "type":
        return el_local == "animateTransform" and value in _TRANSFORM_TYPES
    if name == "dur":
        secs = _clock_seconds(value)
        return secs is not None and 1.0 <= secs <= 20.0
    if name == "begin":
        return _clock_seconds(value) is not None
    if name == "repeatCount":
        return value == "indefinite" or bool(_POSNUM_RE.match(value.strip()))
    if name in ("values", "keyPoints"):
        return value.strip() != "" and bool(_NUMLIST_RE.match(value))
    if name == "path":
        return value.strip() != "" and bool(_PATH_RE.match(value))
    if name in ("additive", "accumulate"):
        return value in ("replace", "sum", "none")
    if name == "rotate":
        return value in ("auto", "auto-reverse") or _clock_seconds(value) is not None
    return False


def _check_element(el, is_root=False, allow_animation=False):
    """Recursively validate one element and its subtree. Returns True if the
    whole subtree is clean, False on the first violation (short-circuits)."""
    local, uri = _local_name(el.tag)
    if uri is not None and uri != _SVG_NS:
        return False
    if local in ANIM_ELEMENTS:
        if not allow_animation:
            return False
        for attr_name in el.attrib:
            attr_local, attr_uri = _local_name(attr_name)
            if attr_uri == _XLINK_NS:
                return False
            if attr_local.lower().startswith("on") or attr_local in ("href", "style"):
                return False
            if attr_local not in ANIM_ATTRS:
                return False
            if not _valid_anim_attr(local, attr_local, el.attrib[attr_name]):
                return False
        for _child in el:
            return False  # animation elements carry no children in this subset
        return True
    if local == "svg" and not is_root:
        return False  # nested svg elements not allowed
    if local not in ALLOWED_ELEMENTS:
        return False
    for attr_name in el.attrib:
        attr_local, attr_uri = _local_name(attr_name)
        if attr_uri == _XLINK_NS:
            return False  # xlink:href (or any other xlink:* attribute) — reject outright
        if attr_local.lower().startswith("on"):
            return False  # onclick, onload, ... — belt-and-suspenders over the allowlist below
        if attr_local in ("href", "style"):
            return False
        if attr_local not in ALLOWED_ATTRS:
            return False
        # Validate url() values in paint and reference attributes
        if attr_local in ("fill", "stroke", "marker-start", "marker-end"):
            attr_value = el.attrib[attr_name]
            if "url(" in attr_value.lower():
                # Must be a same-document fragment reference: url(#...)
                if not re.match(r'^\s*url\s*\(\s*#[\w-]+\s*\)\s*$', attr_value, re.IGNORECASE):
                    return False
    for child in el:
        if not _check_element(child, allow_animation=allow_animation):  # is_root=False for children
            return False
    return True


def _strip_namespace(el):
    """Rewrite this element's tag (and its children's, recursively) to drop the SVG
    namespace URI, so ET's serializer emits clean `<rect .../>` instead of
    `<ns0:rect xmlns:ns0="...">`. Attribute names need no rewriting: only bare or
    xlink-namespaced attributes are possible at this point, and xlink ones were
    already rejected by _check_element."""
    local, _ = _local_name(el.tag)
    el.tag = local
    for child in el:
        _strip_namespace(child)


def sanitize_svg(code, *, allow_animation=False):
    """Strict allowlist SVG sanitizer. Returns canonical sanitized SVG markup, or
    None on any violation (never repairs). allow_animation=False (default) is the
    static path, unchanged. allow_animation=True additionally permits the
    animateTransform/animateMotion subset with value restrictions and enforces
    the <=30 drawn / <=8 animation element budgets."""
    if not isinstance(code, str) or not code.strip():
        return None
    if len(code.encode("utf-8")) > MAX_INPUT_BYTES:
        return None
    # Entity-expansion (billion laughs) guard: we never need DTDs/entities in a figure.
    lowered = code.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        return None
    try:
        root = ET.fromstring(code)
    except ET.ParseError:
        return None
    local, uri = _local_name(root.tag)
    if uri is not None and uri != _SVG_NS:
        return None
    if local != "svg":
        return None
    if "viewBox" not in root.attrib:
        return None
    # The root must NOT carry width/height (CSS sizes it) — width/height ARE allowlisted
    # attributes generically (needed on shapes like <rect>), so this must be checked here
    # explicitly, before the generic walk below would otherwise let them through.
    if "width" in root.attrib or "height" in root.attrib:
        return None
    if not _check_element(root, is_root=True, allow_animation=allow_animation):
        return None
    if allow_animation:
        all_els = list(root.iter())
        anim = sum(1 for e in all_els if _local_name(e.tag)[0] in ANIM_ELEMENTS)
        drawn = len(all_els) - anim - 1  # minus the root <svg>
        if anim > _MAX_ANIM_ELEMENTS or drawn > _MAX_DRAWN_ELEMENTS:
            return None
    _strip_namespace(root)
    return ET.tostring(root, encoding="unicode")
