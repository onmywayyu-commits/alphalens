import json
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook, load_workbook
from PIL import Image

from scripts.import_x_posts import COLUMNS, audit_rows, classify_url, parse_date
from scripts.x_archive_models import ImportResult
from scripts.x_archive_output import render_report, write_outputs


class FieldParsingTests(unittest.TestCase):
    def test_dates_preserve_day_precision_and_reject_invalid_values(self):
        self.assertEqual(parse_date("26.11.4"), date(2026, 11, 4))
        self.assertEqual(parse_date("2027-01-02"), date(2027, 1, 2))
        self.assertEqual(parse_date(date(2026, 11, 20)), date(2026, 11, 20))
        self.assertIsNone(parse_date("26.02.31"))
        self.assertIsNone(parse_date("26.11-20"))

    def test_status_ids_are_strings_and_hosts_are_validated(self):
        link = classify_url("http://twitter.com/SemiAnalysis_/status/2123465108193992939/photo/1?s=22")
        self.assertEqual(link.post_id, "2123465108193992939")
        self.assertEqual(link.author_handle, "@SemiAnalysis_")
        self.assertEqual(link.url, "https://x.com/SemiAnalysis_/status/2123465108193992939")
        self.assertEqual(classify_url("https://x.com/SemiAnalysis_").kind, "profile")
        self.assertIsNone(classify_url("https://x.com/i/web/status/123").author_handle)
        self.assertEqual(classify_url("https://x.com.fake.test/alpha/status/123").kind, "invalid")
        self.assertEqual(classify_url("https://bad.test@x.com/alpha/status/123").kind, "invalid")
        self.assertEqual(classify_url("https://x.com/alpha/status/abc").kind, "other_x_path")


class WorkbookImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "raw/x_posts.xlsx"
        self.source.parent.mkdir()
        images = self.source.parent / "media"
        images.mkdir()
        for filename in ("first.jpg", "second.png", "third.webp"):
            Image.new("RGB", (4, 4), "blue").save(images / filename)
        (images / "broken.png").write_bytes(b"invalid image")

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append(COLUMNS)
        sheet.append([
            "@Watch", "Archived Author", "26.11.4", "  Original wording\n(1/2)  ",
            "https://x.com/Author/status/111", "media/first.jpg\nmedia/second.png",
            "Quoted wording", "https://x.com/Quoted/status/222",
        ])
        sheet.append([
            "@Watch", "Archived Author", "26.11.4", "Another part（2/2）",
            "https://twitter.com/Author/status/111?s=9", "media/missing.jpg", None,
            "https://x.com/Quoted/status/222",
        ])
        sheet.append([
            None, None, "26.02.31", "Source may be copied",
            "https://x.com/Quoted/status/222", "media/third.webp;media/broken.png", "Link missing", None,
        ])
        sheet.append([None, None, "26.11.4"])
        sheet.append(["@Watch", "A", "26.11.5", "Another observation", None, None, None, None])
        sheet.append(["@Watch", "A", "26.11.6", "A profile link", "https://x.com/Watch"])
        sheet.append(["@Watch", "A", "26.11.6", "A bad link", "https://wrong.test/Watch/status/10"])
        sheet.append(["@Watch", "A", "26.11.6", "A hyperlink with no URL as its label", "Open post"])
        sheet["E9"].hyperlink = "https://x.com/Watch/status/333"
        workbook.save(self.source)
        workbook.close()

    def test_preserves_records_metadata_links_issues_and_media(self):
        original_bytes = self.source.read_bytes()
        result = audit_rows(self.source, "Sheet1")
        self.assertEqual(self.source.read_bytes(), original_bytes)
        self.assertEqual(result.data_rows, 8)
        self.assertEqual(len(result.posts), 7)
        by_row = {post.excel_row: post for post in result.posts}
        first, second, third = (by_row[i] for i in (2, 3, 4))

        self.assertEqual(first.content, "  Original wording\n(1/2)  ")
        self.assertEqual(first.post_id, second.post_id)
        self.assertNotEqual(first.record_id, second.record_id)
        self.assertEqual(first.monitored_account, "@Watch")
        self.assertEqual(first.source_author_handle, "@Author")
        self.assertIsNone(third.monitored_account)
        self.assertIsNone(third.posted_date)
        self.assertEqual(third.posted_date_raw, "26.02.31")
        self.assertIsNone(first.posted_at)
        self.assertIsNone(first.collected_at)
        self.assertEqual(first.text_origin_status, "unknown_manual_entry")
        self.assertEqual(first.content_verification, "pending")
        self.assertEqual(first.source_verification, "pending")
        self.assertEqual(by_row[6].source_verification, "missing")
        self.assertEqual(by_row[7].source_url_status, "profile")
        self.assertIsNone(by_row[7].post_id)
        self.assertEqual(by_row[8].source_url_status, "invalid")
        self.assertEqual(by_row[9].post_id, "333")

        self.assertEqual(first.quoted_post_id, "222")
        self.assertEqual(first.quoted_author_handle, "@Quoted")
        self.assertEqual(first.quoted_content, "Quoted wording")
        self.assertEqual([(image.position, image.local_path) for image in first.media], [
            (1, "media/first.jpg"), (2, "media/second.png"),
        ])
        self.assertTrue(all(image.public_path is None for post in result.posts for image in post.media))
        self.assertFalse(second.media[0].exists)
        self.assertEqual(third.media[0].availability, "available")
        self.assertEqual(third.media[1].availability, "invalid_file")
        self.assertTrue(third.media[1].exists)

        issues = {(issue.code, tuple(issue.excel_rows)) for issue in result.issues}
        for expected in (
            ("duplicate_source_link", (2, 3)), ("source_author_mismatch", (2,)),
            ("missing_quoted_content", (3,)), ("missing_quoted_url", (4,)),
            ("missing_image", (3,)), ("invalid_date", (4,)), ("placeholder_row", (5,)),
        ):
            self.assertIn(expected, issues)
        relations = {(relation.kind, tuple(relation.excel_rows)) for relation in result.relations}
        self.assertIn(("numbered_thread_candidate", (2, 3)), relations)
        self.assertIn(("archive_quote", (2, 4)), relations)
        self.assertIn(("shared_post_id", (2, 3)), relations)

    def test_safe_filename_fallback_preserves_review_status(self):
        workbook = load_workbook(self.source)
        workbook["Sheet1"]["F2"] = r"Z:\Unavailable\first.jpg"
        workbook.save(self.source)
        workbook.close()
        result = audit_rows(self.source, "Sheet1")
        media = result.posts[0].media[0]
        self.assertEqual(media.local_path, "media/first.jpg")
        self.assertEqual(media.availability, "filename_match")
        self.assertTrue(media.exists)
        self.assertNotIn("Unavailable", result.model_dump_json())

    def test_snapshot_is_idempotent_and_new_date_retains_old_snapshot(self):
        output = self.directory / "processed"
        report = self.directory / "docs/DATA_QUALITY_REPORT.md"
        initial = audit_rows(self.source, "Sheet1")
        snapshot = write_outputs(initial, output, report)
        original_snapshot = (snapshot / "posts.json").read_bytes()
        self.assertEqual(write_outputs(audit_rows(self.source, "Sheet1"), output, report), snapshot)
        self.assertEqual((output / "posts.json").read_bytes(), original_snapshot)

        workbook = load_workbook(self.source)
        workbook["Sheet1"].append(["@Watch", "A", "2027-01-02", "New date"])
        workbook.save(self.source)
        workbook.close()
        new = audit_rows(self.source, "Sheet1")
        updated_snapshot = write_outputs(new, output, report)
        self.assertNotEqual(updated_snapshot, snapshot)
        self.assertEqual((snapshot / "posts.json").read_bytes(), original_snapshot)
        self.assertEqual(new.posts[0].record_id, initial.posts[0].record_id)
        self.assertEqual(new.posts[-1].posted_date, date(2027, 1, 2))
        self.assertEqual(ImportResult.model_validate_json((output / "posts.json").read_bytes()), new)
        self.assertIn("| 2027-01-02 | 1 |", report.read_text(encoding="utf-8"))
        self.assertEqual(report.read_text(encoding="utf-8"), render_report(new))

    def test_rejects_unknown_sheet_and_missing_column(self):
        with self.assertRaisesRegex(ValueError, "找不到工作表"):
            audit_rows(self.source, "Invalid")
        workbook = load_workbook(self.source)
        workbook["Sheet1"]["F1"] = "wrong"
        workbook.save(self.source)
        workbook.close()
        with self.assertRaisesRegex(ValueError, "photo"):
            audit_rows(self.source, "Sheet1")


class UserArchiveChecks(unittest.TestCase):
    def test_current_workbook_reconciles_with_emitted_records(self):
        path = Path("data/raw/x_posts.xlsx")
        if not path.is_file():
            self.skipTest("本地未配置原始工作簿")
        original = path.read_bytes()
        result = audit_rows(path, "Sheet1")
        book = load_workbook(path, read_only=True)
        try:
            source_text = {
                i: cells[3]
                for i, cells in enumerate(book["Sheet1"].iter_rows(min_row=2, values_only=True), 2)
                if cells[3] is not None and str(cells[3]).strip()
            }
        finally:
            book.close()
        self.assertEqual({post.excel_row: post.content for post in result.posts}, source_text)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len({post.record_id for post in result.posts}), len(source_text))
        self.assertTrue(all(post.posted_at is None and post.analysis_at is None for post in result.posts))
        data = json.loads(result.model_dump_json())
        self.assertEqual(Counter(post["source_url_status"] for post in data["posts"])["status"],
                         sum(post.post_id is not None for post in result.posts))

