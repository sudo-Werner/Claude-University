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
    "stroke-width", "stroke-dasharray", "font-size", "font-family",
    "font-weight", "text-anchor", "dominant-baseline", "opacity",
    "fill-opacity", "marker-end", "marker-start", "id", "class",
}

# Prompt copy shared by generation.py's _IMAGES_BLOCK and images.py's backfill_prompt —
# lives here (not in generation.py or images.py) so neither of those two modules needs
# to import the other just for this string (images.py already needs sanitize_svg above;
# generation.py already imports images.py — putting this text in either of THEM would
# risk a circular import).
DRAWN_FIGURE_GUIDANCE = (
    "\n\nA figure slot may also be a diagram Claude draws itself, as code — no extra "
    "image call, no URL. Choose the figure type by what the content needs: concrete "
    "identification (anatomy, organisms, objects) needs a web-image; a process, flow, "
    "sequence, hierarchy, or timeline needs mermaid; a labeled spatial schematic that "
    "mermaid cannot express needs svg (keep it simple: at most ~25 elements); "
    "quantitative data needs mermaid xychart-beta or pie. When a diagram would be too "
    "complex to draw clearly in code, prefer a web-image slot instead.\n"
    '  A mermaid slot: {"type": "mermaid", "code": "<mermaid source>", "caption": '
    '"<one sentence saying what to NOTICE>"}.\n'
    '  An svg slot: {"type": "svg", "code": "<svg ...>...</svg>", "caption": "<one '
    'sentence saying what to NOTICE>"}. SVG authoring rules: fixed viewBox="0 0 800 '
    '500"; label every part with a <text> element INSIDE the drawing itself, never a '
    "separate legend; font-size at least 14px; use simple flat colors that read clearly "
    "on a light card.\n"
    '  A web-image slot may also state "type": "web-image" explicitly (omitting type '
    "still defaults to web-image).\n"
)


def _local_name(tag):
    """Strip a Clark-notation namespace (e.g. '{http://www.w3.org/2000/svg}rect' ->
    ('rect', 'http://www.w3.org/2000/svg')) so the allowlist check is namespace-aware
    but not namespace-syntax-dependent. Returns (local_name, namespace_uri_or_None)."""
    if tag.startswith("{"):
        uri, _, local = tag[1:].partition("}")
        return local, uri
    return tag, None


def _check_element(el, is_root=False):
    """Recursively validate one element and its subtree against the allowlists.
    Returns True if the whole subtree is clean, False on the first violation
    (short-circuits — the caller drops the whole figure on any False)."""
    local, uri = _local_name(el.tag)
    if uri is not None and uri != _SVG_NS:
        return False
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
        if not _check_element(child):  # is_root=False for children
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


def sanitize_svg(code):
    """Strict allowlist SVG sanitizer. Returns canonical sanitized SVG markup, or
    None if code is empty/not a string, oversized (>8KB), unparseable XML, not
    rooted at <svg>, missing a viewBox, carries a width/height on the root, or
    contains ANY element, attribute, on* handler, href/xlink:href, or style not on
    the allowlist. Never repairs — a violation drops the whole figure, it is never
    partially cleaned."""
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
    if not _check_element(root, is_root=True):
        return None
    _strip_namespace(root)
    return ET.tostring(root, encoding="unicode")
