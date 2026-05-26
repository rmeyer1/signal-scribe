from signal_scribe.sec_client import html_to_text


def test_html_to_text_removes_markup_and_compacts_whitespace():
    html = "<html><body><h1>Item 1A</h1><p>Risk&nbsp;factors</p><script>bad()</script></body></html>"

    text = html_to_text(html)

    assert "Item 1A" in text
    assert "Risk factors" in text
    assert "bad()" not in text
    assert "<p>" not in text
