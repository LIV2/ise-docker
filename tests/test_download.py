import hashlib
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = SourceFileLoader("download_installer", str(ROOT / "download-installer"))
spec = importlib.util.spec_from_loader(loader.name, loader)
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


class DownloadTests(unittest.TestCase):
    def test_import_verifies_before_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source.tar", Path(tmp) / "target.tar"
            source.write_bytes(b"corrupt")
            target.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                downloader.import_archive(source, target)
            self.assertEqual(target.read_bytes(), b"previous")
            with patch.object(downloader, "MD5", hashlib.md5(b"corrupt").hexdigest()):
                downloader.import_archive(source, target)
            self.assertEqual(target.read_bytes(), b"corrupt")

    def test_direct_download_resumes_and_keeps_token_out_of_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installer.tar"
            partial = Path(str(target) + ".part")
            partial.write_bytes(b"start")
            url = "https://download.amd.com/installer.tar?token=private"

            def curl(argv, **kwargs):
                self.assertNotIn(url, argv)
                self.assertIn(url, kwargs["input"])
                self.assertEqual(argv[argv.index("--continue-at") + 1], "-")
                self.assertEqual(partial.read_bytes(), b"start")
                partial.write_bytes(b"complete")
                return subprocess.CompletedProcess(argv, 0)

            with patch.object(downloader.subprocess, "run", side_effect=curl), \
                    patch.object(downloader, "MD5", hashlib.md5(b"complete").hexdigest()):
                downloader.download(url, target)
            self.assertEqual(target.read_bytes(), b"complete")
            self.assertFalse(partial.exists())

    def test_error_page_is_not_promoted_or_resumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installer.tar"
            partial = Path(str(target) + ".part")

            def curl(argv, **kwargs):
                partial.write_bytes(b"<html>Sign in</html>")
                return subprocess.CompletedProcess(argv, 0)

            with patch.object(downloader.subprocess, "run", side_effect=curl), \
                    self.assertRaisesRegex(ValueError, "checksum mismatch"):
                downloader.download("https://download.amd.com/installer.tar", target)
            self.assertFalse(target.exists())
            self.assertFalse(partial.exists())
            self.assertTrue(Path(str(target) + ".invalid").exists())

    def test_rejects_non_vendor_or_non_https_url(self):
        for url in ("http://download.amd.com/file", "https://amd.com.evil.test/file",
                    "https://user:password@amd.com/file", "https://amd.com/file\nnext"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                downloader.download(url, Path("unused"))

    def test_browser_candidates_ignore_incomplete_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            complete = folder / downloader.FILENAME
            duplicate = folder / (downloader.FILENAME[:-4] + " (1).tar")
            complete.touch()
            duplicate.touch()
            (folder / (downloader.FILENAME + ".crdownload")).touch()
            self.assertEqual(set(downloader.find_download(folder)), {complete, duplicate})


if __name__ == "__main__":
    unittest.main()
