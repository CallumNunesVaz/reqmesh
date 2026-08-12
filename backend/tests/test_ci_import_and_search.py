"""CI test-result import, project-wide search, and the allocation matrix."""


import pytest

from .conftest import make_req


JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite" tests="2">
  <testcase classname="pkg.Tests" name="VCAF0001" time="1.5"/>
  <testcase classname="pkg.Tests" name="VCAF0002" time="0.5">
    <failure message="expected True, got False">trace</failure>
  </testcase>
</testsuite>"""

# 289 bytes that expand to 100 KB; two more entity levels reach ~10 GB.
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE t [
<!ENTITY a "AAAAAAAAAA">
<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
<!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
<!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">
]>
<testsuite><testcase name="&e;"/></testsuite>"""


def _make_vc(client, project, vc_id, name):
    res = client.post(f"/api/projects/{project}/verification",
                      json={"id": vc_id, "name": name})
    assert res.status_code == 201, res.text
    return res


def _upload(client, project, body, **data):
    return client.post(
        f"/api/projects/{project}/test-results/import",
        files={"file": ("results.xml", body.encode(), "application/xml")},
        data=data or {},
    )


class TestSampleTestResult:
    def test_sample_is_importable_junit_xml(self, client, project):
        """The sample exists so a CI author can see the expected shape, which is
        only true if it round-trips through the importer."""
        res = client.get(f"/api/projects/{project}/test-results/sample")
        assert res.status_code == 200, res.text
        assert res.headers["content-type"].startswith("application/xml")
        assert _upload(client, project, res.text).status_code == 200

    def test_the_path_parameter_is_declared(self, client, project):
        """The handler took no `project_id` while its path template had one, so
        the generated OpenAPI schema described a variable it never defined — a
        path no client generator could fill in. Assert the schema, not just the
        response, since the response was fine throughout."""
        spec = client.get("/openapi.json").json()
        params = spec["paths"]["/api/projects/{project_id}/test-results/sample"]["get"]["parameters"]
        assert any(p["name"] == "project_id" and p["in"] == "path" for p in params)


class TestJunitImport:
    def test_import_updates_verification_case_status(self, client, project):
        _make_vc(client, project, "VCAF0001", "Thrust check")
        _make_vc(client, project, "VCAF0002", "Mass check")

        res = _upload(client, project, JUNIT)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["parsed"] == 2
        assert body["matched"] == 2
        assert body["updated"] == 2

        vc1 = client.get(f"/api/projects/{project}/verification/VCAF0001").json()
        vc2 = client.get(f"/api/projects/{project}/verification/VCAF0002").json()
        assert vc1["status"] == "passed"
        assert vc2["status"] == "failed"

    def test_dry_run_changes_nothing(self, client, project):
        _make_vc(client, project, "VCAF0001", "Thrust check")

        res = _upload(client, project, JUNIT, dry_run="true")
        assert res.status_code == 200, res.text
        assert res.json()["updated"] == 0

        vc = client.get(f"/api/projects/{project}/verification/VCAF0001").json()
        assert vc["status"] != "passed"

    def test_response_reports_the_detected_format(self, client, project):
        """`getattr(results, '__format__', 'unknown')` returned list.__format__ —
        a bound method — which is not JSON-serialisable."""
        _make_vc(client, project, "VCAF0001", "Thrust check")
        res = _upload(client, project, JUNIT, format="auto")
        assert res.status_code == 200, res.text
        assert res.json()["detected_format"] == "junit"

    def test_unknown_format_is_rejected(self, client, project):
        res = _upload(client, project, JUNIT, format="nonsense")
        assert res.status_code == 400


class TestXmlEntityExpansion:
    def test_doctype_is_refused(self, client, project):
        """The ReqIF importer already refuses a DOCTYPE (F-15). This parser is a
        second XML entry point and needs the same guard — ElementTree blocks
        *external* entities but happily expands internal ones."""
        res = _upload(client, project, BILLION_LAUGHS)
        assert res.status_code == 400
        assert "doctype" in res.json()["detail"].lower()

    def test_parser_refuses_doctype_directly(self):
        from app.services.test_result_import import parse_junit_xml

        with pytest.raises(ValueError, match="(?i)doctype"):
            parse_junit_xml(BILLION_LAUGHS.encode())


class TestMatcherPrecision:
    def test_a_short_vc_name_does_not_swallow_every_test(self, client, project):
        """Rule 2 matched on bare substring, so a VC named 'Test' (or any short
        common word) claimed every incoming result and silently overwrote the
        verification status of the wrong case."""
        _make_vc(client, project, "VCAF0001", "Test")
        _make_vc(client, project, "VCAF0002", "Mass budget check")

        xml = """<?xml version="1.0"?>
<testsuite name="s">
  <testcase classname="pkg" name="Mass budget check" time="1"/>
</testsuite>"""
        res = _upload(client, project, xml)
        assert res.status_code == 200, res.text

        # The result belongs to VCAF0002, not the VC that happens to be called "Test".
        vc1 = client.get(f"/api/projects/{project}/verification/VCAF0001").json()
        vc2 = client.get(f"/api/projects/{project}/verification/VCAF0002").json()
        assert vc2["status"] == "passed"
        assert vc1["status"] != "passed"


class TestProjectSearch:
    def test_finds_a_requirement_by_name(self, client, project):
        make_req(client, project, "SYST0001", name="Landing gear retraction")

        res = client.get(f"/api/projects/{project}/search", params={"q": "landing"})
        assert res.status_code == 200
        hits = res.json()["results"]
        assert any(h["id"] == "SYST0001" and h["kind"] == "requirement" for h in hits)

    def test_snippet_preserves_original_casing(self, client, project):
        """Snippets were sliced out of the lowercased haystack, so every result
        rendered in the palette as all-lowercase."""
        make_req(client, project, "SYST0001", name="Gear",
                 description="<p>The NATO Standard Agreement applies here.</p>")

        res = client.get(f"/api/projects/{project}/search", params={"q": "standard"})
        hit = next(h for h in res.json()["results"] if h["id"] == "SYST0001")
        assert "NATO" in hit["snippet"], hit["snippet"]

    def test_snippet_contains_no_markup(self, client, project):
        make_req(client, project, "SYST0001", name="Gear",
                 description="<p>alpha <strong>bravo</strong> charlie</p>")

        res = client.get(f"/api/projects/{project}/search", params={"q": "bravo"})
        hit = next(h for h in res.json()["results"] if h["id"] == "SYST0001")
        assert "<" not in hit["snippet"]

    def test_export_and_search_agree_on_stripped_html(self, client, project):
        """The same HTML description renders to the same plain text in a CSV
        export and in a search snippet — block tags become spaces, not nothing,
        so ``<p>a</p><p>b</p>`` never welds into ``ab``."""
        import csv
        import io

        from app.core.dependencies import get_store
        from app.services.table_io import export_table

        make_req(client, project, "SYST0001", name="Widget",
                 description="<p>Alpha</p><p>Beta</p>")

        store = get_store(project)
        rows = list(csv.DictReader(io.StringIO(export_table(store, "csv"))))
        exported = next(r["description"] for r in rows if r["id"] == "SYST0001")

        res = client.get(f"/api/projects/{project}/search", params={"q": "beta"})
        hit = next(h for h in res.json()["results"] if h["id"] == "SYST0001")

        def norm(s: str) -> str:
            return " ".join(s.split())

        assert norm(exported) == "Alpha Beta"
        assert norm(hit["snippet"]) == "Alpha Beta"

    def test_short_queries_return_nothing(self, client, project):
        make_req(client, project, "SYST0001", name="Gear")
        assert client.get(f"/api/projects/{project}/search",
                          params={"q": "a"}).json()["results"] == []

    def test_kind_filter_restricts_results(self, client, project):
        make_req(client, project, "SYST0001", name="Widget")
        client.post(f"/api/projects/{project}/components",
                    json={"id": "COMP1", "name": "Widget housing"})

        res = client.get(f"/api/projects/{project}/search",
                         params={"q": "widget", "kind": "component"})
        kinds = {h["kind"] for h in res.json()["results"]}
        assert kinds == {"component"}


class TestAllocationMatrix:
    def test_matrix_reports_allocation(self, client, project):
        make_req(client, project, "SYST0001")
        client.post(f"/api/projects/{project}/components",
                    json={"id": "COMP1", "name": "Engine"})

        res = client.post(f"/api/projects/{project}/allocation",
                          json={"req_id": "SYST0001", "component_id": "COMP1",
                                "allocated": True})
        assert res.status_code == 200, res.text

        m = client.get(f"/api/projects/{project}/allocation-matrix").json()
        assert m["allocated"] == 1
        row = next(r for r in m["rows"] if r["req_id"] == "SYST0001")
        assert row["cells"]["COMP1"] is True

    def test_deallocating_one_component_keeps_the_others(self, client, project):
        """allocated_to was cleared unconditionally on deallocation, so removing
        one component blanked the field while another still satisfied the
        requirement — leaving the matrix and the field disagreeing."""
        make_req(client, project, "SYST0001")
        for cid, name in (("COMP1", "Engine"), ("COMP2", "Pylon")):
            client.post(f"/api/projects/{project}/components",
                        json={"id": cid, "name": name})
            client.post(f"/api/projects/{project}/allocation",
                        json={"req_id": "SYST0001", "component_id": cid, "allocated": True})

        client.post(f"/api/projects/{project}/allocation",
                    json={"req_id": "SYST0001", "component_id": "COMP2", "allocated": False})

        req = client.get(f"/api/projects/{project}/requirements/SYST0001").json()
        assert req["allocated_to"] != "", "still satisfied by COMP1"

        m = client.get(f"/api/projects/{project}/allocation-matrix").json()
        row = next(r for r in m["rows"] if r["req_id"] == "SYST0001")
        assert row["cells"]["COMP1"] is True
        assert row["cells"]["COMP2"] is False
