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
