from backend import figures


def test_sanitize_svg_accepts_labeled_schematic_canonical_output():
    src = ('<svg viewBox="0 0 800 500"><rect x="10" y="10" width="80" height="40" '
           'fill="#eee" stroke="#333"/><text x="20" y="35" font-size="14">Pump</text></svg>')
    out = figures.sanitize_svg(src)
    assert out == ('<svg viewBox="0 0 800 500"><rect x="10" y="10" width="80" height="40" '
                    'fill="#eee" stroke="#333" /><text x="20" y="35" font-size="14">Pump</text></svg>')


def test_sanitize_svg_strips_default_xmlns_from_output():
    src = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">'
           '<g><circle cx="50" cy="50" r="20" fill="#fff"/>'
           '<text x="30" y="80" font-size="14">Valve</text></g></svg>')
    out = figures.sanitize_svg(src)
    assert "xmlns" not in out
    assert out == ('<svg viewBox="0 0 800 500"><g><circle cx="50" cy="50" r="20" fill="#fff" />'
                    '<text x="30" y="80" font-size="14">Valve</text></g></svg>')


def test_sanitize_svg_rejects_script_element():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><script>alert(1)</script></svg>') is None


def test_sanitize_svg_rejects_foreignobject():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><foreignObject><div>x</div></foreignObject></svg>') is None


def test_sanitize_svg_rejects_onclick_attribute():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect onclick="alert(1)" width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_href():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><a href="https://evil.example"><rect width="10" height="10"/></a></svg>') is None


def test_sanitize_svg_rejects_xlink_href():
    src = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'viewBox="0 0 800 500"><rect xlink:href="evil.png" width="10" height="10"/></svg>')
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_style_element():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><style>rect{fill:red}</style><rect width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_style_attribute():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect style="fill:red" width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_missing_viewbox():
    assert figures.sanitize_svg('<svg><rect width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_root_width_or_height():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500" width="800"><rect width="10" height="10"/></svg>') is None
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500" height="500"><rect width="10" height="10"/></svg>') is None


def test_sanitize_svg_allows_width_height_on_non_root_elements():
    out = figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>')
    assert out == '<svg viewBox="0 0 800 500"><rect width="10" height="10" /></svg>'


def test_sanitize_svg_rejects_oversize_input():
    big = '<svg viewBox="0 0 800 500">' + ('<g></g>' * 3000) + '</svg>'
    assert len(big.encode("utf-8")) > figures.MAX_INPUT_BYTES
    assert figures.sanitize_svg(big) is None


def test_sanitize_svg_rejects_unparseable_xml():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect></svg>') is None


def test_sanitize_svg_rejects_non_svg_root():
    assert figures.sanitize_svg('<div viewBox="0 0 800 500"></div>') is None


def test_sanitize_svg_rejects_disallowed_element_and_attribute():
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><use href="#x"/></svg>') is None
    assert figures.sanitize_svg('<svg viewBox="0 0 800 500"><rect cursor="pointer" width="10" height="10"/></svg>') is None


def test_sanitize_svg_rejects_empty_or_non_string():
    assert figures.sanitize_svg("") is None
    assert figures.sanitize_svg(None) is None
    assert figures.sanitize_svg("   ") is None


def test_drawn_figure_guidance_mentions_both_types_and_authoring_rules():
    g = figures.DRAWN_FIGURE_GUIDANCE
    assert '"type": "mermaid"' in g
    assert '"type": "svg"' in g
    assert 'viewBox="0 0 800 500"' in g
    assert "14px" in g
    assert "~25 elements" in g


# Finding 1: Entity-expansion (billion laughs) guard tests
def test_sanitize_svg_rejects_doctype_declaration():
    src = '<!DOCTYPE svg><svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_entity_expansion_billion_laughs_payload():
    # Simplified billion-laughs attack: nested entities
    src = '''<!DOCTYPE svg [
        <!ENTITY lol "lol">
        <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">
    ]>
    <svg viewBox="0 0 800 500"><text>&lol2;</text></svg>'''
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_entity_declaration():
    src = '<!ENTITY test "test"><svg viewBox="0 0 800 500"><rect width="10" height="10"/></svg>'
    assert figures.sanitize_svg(src) is None


# Finding 2: url() attribute value validation tests
def test_sanitize_svg_rejects_external_url_in_stroke():
    src = '<svg viewBox="0 0 800 500"><rect width="10" height="10" stroke="url(https://evil.example/x.svg#a)"/></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_external_url_in_fill():
    src = '<svg viewBox="0 0 800 500"><rect width="10" height="10" fill="url(http://evil.example/y.svg#b)"/></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_external_url_in_marker_end():
    src = '<svg viewBox="0 0 800 500"><line x1="10" y1="10" x2="100" y2="100" marker-end="url(http://x/y#a)"/></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_javascript_url_in_marker_start():
    src = '<svg viewBox="0 0 800 500"><line x1="10" y1="10" x2="100" y2="100" marker-start="url(javascript:alert(1))"/></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_invalid_url_syntax():
    src = '<svg viewBox="0 0 800 500"><rect width="10" height="10" fill="url(no-hash)"/></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_accepts_valid_same_doc_url_fragment_in_marker_end():
    src = '<svg viewBox="0 0 800 500"><defs><marker id="arrow" viewBox="0 0 10 10"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#333"/></marker></defs><line x1="10" y1="10" x2="100" y2="100" stroke="#000" marker-end="url(#arrow)"/></svg>'
    out = figures.sanitize_svg(src)
    assert out is not None
    assert 'marker-end="url(#arrow)"' in out


def test_sanitize_svg_accepts_valid_same_doc_url_with_whitespace():
    src = '<svg viewBox="0 0 800 500"><defs><marker id="m1" viewBox="0 0 10 10"/></defs><line x1="0" y1="0" x2="100" y2="100" marker-end="url( #m1 )"/></svg>'
    out = figures.sanitize_svg(src)
    assert out is not None


# Finding 3: Nested svg rejection tests
def test_sanitize_svg_rejects_nested_svg():
    src = '<svg viewBox="0 0 800 500"><svg viewBox="0 0 100 100"><rect width="10" height="10"/></svg></svg>'
    assert figures.sanitize_svg(src) is None


def test_sanitize_svg_rejects_deeply_nested_svg():
    src = '<svg viewBox="0 0 800 500"><g><svg viewBox="0 0 100 100"><rect width="10" height="10"/></svg></g></svg>'
    assert figures.sanitize_svg(src) is None


# Regression: ensure canonical test still passes
def test_sanitize_svg_regression_canonical_labeled_schematic():
    src = ('<svg viewBox="0 0 800 500"><rect x="10" y="10" width="80" height="40" '
           'fill="#eee" stroke="#333"/><text x="20" y="35" font-size="14">Pump</text></svg>')
    out = figures.sanitize_svg(src)
    assert out == ('<svg viewBox="0 0 800 500"><rect x="10" y="10" width="80" height="40" '
                    'fill="#eee" stroke="#333" /><text x="20" y="35" font-size="14">Pump</text></svg>')


# Contract lock: a figure authored to the on-brand SVG style guide (flat fill +
# fill-opacity tint for depth, a <polygon> arrowhead, an in-drawing <text> label) must
# stay sanitizer-legal. Guards DRAWN_FIGURE_GUIDANCE's documented style against a future
# allowlist change silently breaking it.
def test_sanitize_svg_accepts_style_guide_exemplar():
    src = (
        '<svg viewBox="0 0 800 500">'
        '<rect x="40" y="40" width="200" height="120" fill="#7c6aff" fill-opacity="0.14" '
        'stroke="#7c6aff" stroke-width="2"/>'
        '<polygon points="300,90 340,100 300,110" fill="#241f1a"/>'
        '<line x1="240" y1="100" x2="300" y2="100" stroke="#241f1a" stroke-width="2"/>'
        '<text x="60" y="105" font-size="16" fill="#241f1a">Left atrium</text>'
        '</svg>'
    )
    assert figures.sanitize_svg(src) is not None


def test_sanitize_svg_accepts_stroke_linecap_and_linejoin():
    src = ('<svg viewBox="0 0 800 500"><path d="M10 10 L90 90" stroke="#333" '
           'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>')
    out = figures.sanitize_svg(src)
    assert out is not None
    assert "stroke-linecap" in out and "stroke-linejoin" in out


def test_valid_image_slot_shared_helper():
    from backend import figures
    assert figures.valid_image_slot({"query": "q", "caption": "c"}) is True
    assert figures.valid_image_slot({"type": "svg", "code": "<svg/>", "caption": "c"}) is True
    assert figures.valid_image_slot({"type": "mermaid", "code": "pie", "caption": "c"}) is True
    assert figures.valid_image_slot({"type": "svg", "code": "", "caption": "c"}) is False
    assert figures.valid_image_slot({"type": "web-image", "query": "", "caption": "c"}) is False
    assert figures.valid_image_slot({"type": "bogus", "code": "x", "caption": "c"}) is False
    assert figures.valid_image_slot("not a dict") is False


def test_drawn_guidance_has_no_photo_as_fallback_framing():
    text = figures.DRAWN_FIGURE_GUIDANCE.lower()
    assert "too complex to draw" not in text  # the old loser-framing is gone
    assert "recognize a real thing" in text or "recognise a real thing" in text


# --- svg-animated: must be dropped (return None) under allow_animation=True ---
_MAL = '<svg viewBox="0 0 800 500">{}</svg>'

def _drop(inner):
    return figures.sanitize_svg(_MAL.format(inner), allow_animation=True) is None

def test_anim_rejects_set_and_animate_and_mpath():
    assert _drop('<set attributeName="href" to="javascript:alert(1)"/>')
    assert _drop('<animate attributeName="href" values="a;b" dur="2s"/>')
    assert _drop('<animateMotion><mpath xlink:href="#p"/></animateMotion>')

def test_anim_rejects_bad_attributename_and_type_and_events():
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="x" '
                 'type="translate" values="0 0;9 0" dur="2s"/></rect>')
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="matrix" values="1 0 0 1 0 0" dur="2s"/></rect>')
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="translate" values="0 0;9 0" begin="rect.click" dur="2s"/></rect>')
    assert _drop('<circle r="3"><animateMotion attributeName="transform" path="M0,0 L9,0" dur="2s"/></circle>')

def test_anim_rejects_nonnumeric_values_and_bad_dur():
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="translate" values="url(#x)" dur="2s"/></rect>')
    assert _drop('<rect width="9" height="9"><animateTransform attributeName="transform" '
                 'type="scale" values="1;2" dur="99s"/></rect>')  # dur > 20s

def test_anim_rejects_over_budget():
    dots = "".join('<circle r="1"><animateMotion path="M0,0 L9,0" dur="2s"/></circle>'
                   for _ in range(9))  # 9 animation elements > 8
    assert _drop(dots)

def test_anim_elements_still_rejected_without_flag():
    # default allow_animation=False -> animation is not permitted (static path unchanged)
    assert figures.sanitize_svg(_MAL.format(
        '<rect width="9" height="9"><animateTransform attributeName="transform" '
        'type="translate" values="0 0;9 0" dur="2s"/></rect>')) is None

# --- svg-animated: must survive and keep their animation elements ---
def test_anim_accepts_spin_slide_pulse_motion():
    spin = ('<rect x="10" y="10" width="80" height="40" fill="#7c6aff">'
            '<animateTransform attributeName="transform" type="rotate" '
            'values="0 50 30;360 50 30" dur="4s" repeatCount="indefinite"/></rect>')
    slide = ('<rect x="0" y="0" width="20" height="20" fill="#4fa3e8">'
             '<animateTransform attributeName="transform" type="translate" '
             'values="0 0;100 0" dur="2s" repeatCount="indefinite"/></rect>')
    motion = ('<circle r="4" fill="#d6557e"><animateMotion path="M0,0 L200,0" '
              'dur="3s" begin="-0.5s" repeatCount="indefinite"/></circle>')
    for inner in (spin, slide, motion):
        out = figures.sanitize_svg(_MAL.format(inner), allow_animation=True)
        assert out is not None
        assert "animate" in out.lower()

def test_anim_strip_leaves_valid_still_frame():
    # remove every animate* element -> the remainder must still sanitize (static fallback)
    import re as _re
    src = _MAL.format('<circle cx="40" cy="40" r="4" fill="#d6557e">'
                      '<animateMotion path="M0,0 L200,0" dur="3s"/></circle>'
                      '<text x="10" y="20" font-size="14">Blood cell</text>')
    assert figures.sanitize_svg(src, allow_animation=True) is not None
    still = _re.sub(r'<animate[A-Za-z]*\b[^>]*/>', '', src)
    out = figures.sanitize_svg(still)  # allow_animation defaults False
    assert out is not None and "Blood cell" in out


def test_valid_image_slot_accepts_svg_animated():
    from backend import figures
    assert figures.valid_image_slot(
        {"type": "svg-animated", "code": "<svg/>", "caption": "watch the flow"}) is True
    assert figures.valid_image_slot(
        {"type": "svg-animated", "code": "", "caption": "c"}) is False
