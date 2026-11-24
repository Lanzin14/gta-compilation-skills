"""Testes do enquadramento inteligente dos Shorts (gtakit/framing.py)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from gtakit import framing  # noqa: E402


def profile(cols_by_time):
    return [(i / framing.FPS, cols) for i, cols in enumerate(cols_by_time, 1)]


def blob(center_col, width=3, n=32):
    return [100 if abs(c - center_col) <= width // 2 else 0 for c in range(n)]


class Track(unittest.TestCase):
    def test_follows_concentrated_action(self):
        path, conc = framing.track(profile([blob(6)] * 12))
        self.assertAlmostEqual(path[-1][1], 6.5 / 32, delta=0.02)
        self.assertGreater(conc, 0.9)

    def test_spread_action_has_low_concentration(self):
        _, conc = framing.track(profile([[50] * 32] * 12))
        self.assertLess(conc, framing.MIN_CONCENTRATION)

    def test_pan_speed_is_limited(self):
        path, _ = framing.track(profile([blob(3)] * 8 + [blob(28)] * 8), smooth_s=0)
        steps = [abs(b[1] - a[1]) for a, b in zip(path, path[1:])]
        self.assertLessEqual(max(steps), framing.MAX_PAN_PER_S / framing.FPS + 1e-9)

    def test_no_motion_keeps_center(self):
        path, conc = framing.track(profile([[0] * 32] * 6))
        self.assertEqual(path[-1][1], 0.5)
        self.assertEqual(conc, 0.0)

    def test_keyframes_start_at_zero_and_are_bounded(self):
        keys = framing.keyframes([(0.25 * i, 0.1 * i) for i in range(1, 20)])
        self.assertEqual(keys[0][0], 0.0)
        self.assertTrue(all(0.0 <= c <= 1.0 for _, c in keys))


class Layout(unittest.TestCase):
    H = {"id": "h", "width": 1920, "height": 1080}

    def test_auto_choices(self):
        self.assertEqual(framing.choose_layout({"id": "v", "width": 720, "height": 1280}, 0.9)[0], "vertical")
        self.assertEqual(framing.choose_layout(self.H, 0.8)[0], "crop")
        self.assertEqual(framing.choose_layout(self.H, 0.2)[0], "blur")
        self.assertEqual(framing.choose_layout(dict(self.H, facecam={"x": .7, "y": .7, "w": .3, "h": .3}), 0.2)[0], "split")

    def test_split_without_facecam_is_an_error(self):
        with self.assertRaises(ValueError):
            framing.choose_layout(self.H, 0.9, "split")

    def test_filters_contain_expected_geometry(self):
        keys = [(0.0, 0.3), (1.0, 0.4)]
        self.assertIn("crop=1080:1920:x='clip((", framing.base_filter("crop", self.H, keys, 30))
        sp = framing.base_filter("split", dict(self.H, facecam={"x": 0.7, "y": 0.7, "w": 0.3, "h": 0.3}), keys, 60)
        self.assertIn("vstack,fps=60", sp)
        self.assertIn("crop=iw*0.3:ih*0.3:iw*0.7:ih*0.7", sp)


if __name__ == "__main__":
    unittest.main()
