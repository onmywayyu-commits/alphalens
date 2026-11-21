import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook
from PIL import Image

from scripts.import_x_posts import COLUMNS, audit_rows
from scripts.prepare_archive_preview import prepare_preview


class PreviewMediaTests(unittest.TestCase):
    def test_prepares_valid_image_recovers_when_removed_and_keeps_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            media = raw / "media"
            media.mkdir(parents=True)
            image = media / "sample.png"
            Image.new("RGB", (4, 4), "blue").save(image)
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Sheet1"
            sheet.append(COLUMNS)
            sheet.append(["@watch", "Author", "2026-11-20", "Archive text",
                          "https://x.com/watch/status/111", "media/sample.png\nmedia/missing.jpg"])
            sheet.append(["@watch", "Author", "2026-11-20", "Same URL different text",
                          "https://x.com/watch/status/111"])
            input_file = raw / "fixture.xlsx"
            workbook.save(input_file)
            workbook.close()
            result = audit_rows(input_file, "Sheet1")
            preview = root / "cache"
            manifest = root / "processed/media_manifest.json"
            config = {"accounts": [{"handle": "watch"}]}

            self.assertEqual(prepare_preview(result, raw, config, preview, manifest), (2, 1))
            data = json.loads((preview / "dashboard.json").read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "research")
            self.assertEqual(data["posts"][0]["post_id"], data["posts"][1]["post_id"])
            self.assertNotEqual(data["posts"][0]["archive"]["record_id"], data["posts"][1]["archive"]["record_id"])
            self.assertEqual(data["posts"][0]["summary"], None)
            self.assertEqual(data["reports"], [])
            first, second = data["posts"][0]["archive"]["media"]
            filename = Path(first["preview_path"]).name
            self.assertEqual((preview / "media" / filename).read_bytes(), image.read_bytes())
            self.assertEqual(second["availability"], "missing")
            self.assertIsNone(second["preview_path"])
            self.assertTrue(all(
                item["public_path"] is None for item in json.loads(manifest.read_text(encoding="utf-8"))["media"]
            ))

            image.unlink()
            self.assertEqual(prepare_preview(result, raw, config, preview, manifest), (2, 0))
            now = json.loads((preview / "dashboard.json").read_text(encoding="utf-8"))
            self.assertEqual(now["posts"][0]["archive"]["media"][0]["availability"], "missing")
            self.assertIsNone(now["posts"][0]["archive"]["media"][0]["preview_path"])

