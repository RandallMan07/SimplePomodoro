import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from simplepomodoro.theme import Palette, ThemeSource, luminance, parse_palette, readable_text, rgb


class PaletteTests(unittest.TestCase):
    def test_semantic_palette_drives_all_colors(self):
        palette = parse_palette(dict(background="#1e1e2e", foreground="#cdd6f4", accent="#89b4fa", magenta="#cba6f7", yellow="#f9e2af", mode="dark"))
        self.assertEqual(palette.background, "#1e1e2e")
        self.assertEqual(palette.focus, "#89b4fa")
        self.assertEqual(palette.rest, "#cba6f7")
        self.assertEqual(palette.warning, "#f9e2af")
        self.assertFalse(palette.light)
        self.assertEqual(rgb("#ff0080"), (1, 0, 128 / 255))
        self.assertIn("@define-color sp_focus #89b4fa;", palette.definitions())

    def test_ansi_and_short_aliases(self):
        palette = parse_palette(dict(bg="#112233", fg="#ddeeff", color4="#336699", color5="#663399", color3="#997733"))
        self.assertEqual(palette.background, "#112233")
        self.assertEqual(palette.foreground, "#ddeeff")
        self.assertEqual(palette.focus, "#336699")
        self.assertEqual(palette.rest, "#663399")

    def test_untrusted_values_cannot_enter_css(self):
        for value in ("red; } window {color: red}", "#fff", "#12345678", "#123456\n", 123, [], {}):
            with self.subTest(value=value):
                palette = parse_palette(dict(accent=value, background=value, foreground=value))
                self.assertEqual(palette.focus, Palette().focus)
                self.assertEqual(palette.background, Palette().background)
                self.assertNotIn(str(value), palette.definitions())

    def test_light_theme_and_contrast(self):
        palette = parse_palette(dict(background="#ffffff", foreground="#eeeeee", accent="#333333", mode="light"))
        self.assertTrue(palette.light)
        self.assertEqual(palette.foreground, "#000000")
        self.assertEqual(palette.primary_text, "#ffffff")
        self.assertTrue(parse_palette(dict(background="#ffffff")).light)
        self.assertEqual(readable_text("#ffffff"), "#000000")
        self.assertEqual(readable_text("#000000"), "#ffffff")
        self.assertEqual(luminance("#ffffff"), 1)


class ThemeSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "colors.toml"

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_malformed_and_oversized_use_defaults(self):
        source = ThemeSource(self.path)
        self.assertEqual(source.palette, Palette())
        self.path.write_text("invalid ! toml")
        self.assertTrue(source.reload())
        self.assertEqual(source.palette, Palette())
        self.path.write_bytes(b"\xff")
        source.reload()
        self.assertEqual(source.palette, Palette())
        self.path.write_text('accent = "#123456"\n#' + 'x' * 65536)
        source.reload()
        self.assertEqual(source.palette, Palette())

    def test_reload_edits_replacements_and_removal_without_repeated_reads(self):
        self.path.write_text('accent = "#123456"')
        source = ThemeSource(self.path)
        self.assertEqual(source.palette.focus, "#123456")
        with patch.object(Path, "open", side_effect=AssertionError("unchanged file read")):
            self.assertFalse(source.reload())
        replacement = self.root / "replacement.toml"
        replacement.write_text('accent = "#abcdef"')
        replacement.replace(self.path)
        self.assertTrue(source.reload())
        self.assertEqual(source.palette.focus, "#abcdef")
        self.path.unlink()
        self.assertTrue(source.reload())
        self.assertEqual(source.palette, Palette())

    def test_current_theme_symlink_switch_is_detected(self):
        first, second = self.root / "first", self.root / "second"
        first.mkdir()
        second.mkdir()
        (first / "colors.toml").write_text('accent = "#123456"')
        (second / "colors.toml").write_text('accent = "#abcdef"')
        link = self.root / "current"
        link.symlink_to(first, target_is_directory=True)
        source = ThemeSource(link / "colors.toml")
        link.unlink()
        link.symlink_to(second, target_is_directory=True)
        self.assertTrue(source.reload())
        self.assertEqual(source.palette.focus, "#abcdef")

    def test_xdg_path(self):
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": str(self.root)}):
            self.assertEqual(ThemeSource().path, self.root / "omarchy/current/theme/colors.toml")


if __name__ == "__main__":
    unittest.main()
