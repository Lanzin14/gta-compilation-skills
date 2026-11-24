"""Testes de unidade do gtakit (funções puras, sem ffmpeg). Rodar da raiz do repositório:

    python3 -m unittest discover -s tests -p "test_*.py"
"""
import itertools
import pathlib
import random
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from gtakit import analysis, render, rights, timeline, viral  # noqa: E402
from gtakit.__main__ import _from_ytdlp  # noqa: E402
from gtakit.project import Project, check_items, save_json  # noqa: E402

NO_DEAD = {"silence_start": [], "silence_end": [], "freeze_start": [], "freeze_end": []}


class Viral(unittest.TestCase):
    def test_zero_engagement_has_no_division_by_zero(self):
        self.assertEqual(viral.viral_scores([{"id": "a", "likes": 0, "reposts": 0, "comments": 0, "timestamp": 0}], 3600),
                         {"a": 0})

    def test_null_fields_count_as_zero_and_best_gets_100(self):
        s = viral.viral_scores([{"id": "a", "likes": 100, "reposts": None, "comments": None, "timestamp": 0},
                                {"id": "b", "likes": 10, "reposts": 1, "comments": 1, "timestamp": 0}], 7200)
        self.assertEqual(s["a"], 100)
        self.assertLess(s["b"], s["a"])


class Peaks(unittest.TestCase):
    def test_constant_audio_has_no_peaks(self):
        self.assertEqual(analysis.find_peaks([(t / 2, -30.0) for t in range(40)]), ([], None))

    def test_isolated_scream_in_silence_is_found(self):
        w = [(t / 2, float("-inf")) for t in range(30)]
        w[16] = (8.0, -20.0)
        peaks, loudest = analysis.find_peaks(w)
        self.assertEqual(peaks, [8.0])
        self.assertEqual(loudest, (8.0, -20.0))

    def test_silence_never_is_a_peak(self):
        self.assertEqual(analysis.find_peaks([(0.0, float("-inf")), (0.5, float("-inf"))])[0], [])


class DeadTime(unittest.TestCase):
    def test_only_silence_and_freeze_together_at_start_are_cut(self):
        d = {"silence_start": [0.0], "silence_end": [2.0], "freeze_start": [0.0], "freeze_end": [2.5]}
        self.assertEqual(analysis.leading_dead_time(d, 10), 2.0)
        d["freeze_start"] = [1.0]
        self.assertEqual(analysis.leading_dead_time(d, 10), 0.0)

    def test_dead_time_until_end_without_end_marker(self):
        d = {"silence_start": [0.0], "silence_end": [], "freeze_start": [0.0], "freeze_end": [3.0]}
        self.assertEqual(analysis.leading_dead_time(d, 10), 3.0)


class LongVideo(unittest.TestCase):
    def test_long_video_is_cut_around_groups_within_limits(self):
        video = {"id": "v", "local_path": "source/v.mp4", "duration_s": 120.0}
        w = [(t / 2, -35.0) for t in range(240)]
        for t in (30.0, 31.0, 90.0):  # dois grupos: 30–31 s e 90 s
            w[int(t * 2)] = (t, -15.0)
        ms = analysis.analyze_video(video, w, [], NO_DEAD)
        self.assertEqual(len(ms), 2)
        for m in ms:
            self.assertGreaterEqual(m["end"] - m["start"], analysis.MIN_CUT_S)
            self.assertLessEqual(m["end"] - m["start"], analysis.MAX_CUT_S)
            self.assertTrue(m["start"] <= m["peak_time"] <= m["end"])
        self.assertEqual(sorted(m["start"] for m in ms), [26.0, 86.0])

    def test_long_video_never_returns_more_than_three(self):
        video = {"id": "v", "local_path": "x", "duration_s": 400.0}
        w = [(t / 2, -35.0) for t in range(800)]
        for k in range(8):
            w[k * 80] = (k * 40.0, -10.0)
        self.assertLessEqual(len(analysis.analyze_video(video, w, [], NO_DEAD)), analysis.MAX_MOMENTS_PER_VIDEO)


class Timeline(unittest.TestCase):
    def test_short_first_clip_joins_next_and_short_last_joins_previous(self):
        e = timeline.clip_starts([{"moment_id": "a", "clip_dur": 6}, {"moment_id": "b", "clip_dur": 14},
                                  {"moment_id": "c", "clip_dur": 20}, {"moment_id": "d", "clip_dur": 5}])
        self.assertEqual([x["clip_start"] for x in e], [0, 6, 20, 40])
        ch = timeline.chapters(e)
        self.assertEqual([c["moment_ids"] for c in ch], [["a", "b"], ["c", "d"]])
        self.assertTrue(all(c["dur"] >= 10 for c in ch))

    def test_legacy_order_opens_with_second_best_and_closes_with_best(self):
        ms = [{"id": i, "video_id": i, "score": s, "selected": True} for i, s in (("a", 50), ("b", 100), ("c", 75), ("d", 60))]
        self.assertEqual([m["id"] for m in timeline.legacy_order(ms, {})], ["c", "d", "a", "b"])

    def test_timestamp_format(self):
        self.assertEqual(timeline.fmt_ts(65), "01:05")
        self.assertEqual(timeline.fmt_ts(3725), "1:02:05")


def _scenario(rnd, n, creators):
    vids = [{"id": f"v{i}", "author_handle": f"@{rnd.choice(creators)}", "viral_score": rnd.randint(0, 100)} for i in range(n)]
    ms = [{"id": f"m{i:02d}", "video_id": f"v{i}", "score": rnd.randint(40, 100), "start": 0.0,
           "end": float(rnd.randint(6, 70)), "selected": True,
           "ranking": {"criteria": {"reacao": rnd.randint(0, 100), "retencao": rnd.randint(0, 100)}}} for i in range(n)]
    return vids, ms


def _feasible(ms, vids, last):
    who = {v["id"]: v["author_handle"] for v in vids}
    rest = [m for m in ms if m is not last]
    for perm in itertools.permutations(rest):
        seq = list(perm) + [last]
        if all(who[a["video_id"]] != who[b["video_id"]] for a, b in zip(seq, seq[1:])):
            return True
    return False


class SmartOrder(unittest.TestCase):
    def test_closes_with_best_and_never_repeats_creator_when_possible(self):
        rnd = random.Random(42)
        checked = 0
        for _ in range(150):
            vids, ms = _scenario(rnd, rnd.randint(3, 7), ["a", "b", "c"])
            order, notes = timeline.smart_order(ms, vids)
            who = {v["id"]: v["author_handle"] for v in vids}
            best = max(ms, key=lambda m: (m["score"], next(v["viral_score"] for v in vids if v["id"] == m["video_id"]), m["id"]))
            self.assertIs(order[-1], best)
            self.assertEqual(sorted(m["id"] for m in order), sorted(m["id"] for m in ms))
            adjacent_ok = all(who[a["video_id"]] != who[b["video_id"]] for a, b in zip(order, order[1:]))
            if _feasible(ms, vids, best):
                self.assertTrue(adjacent_ok, (notes, [(m["id"], who[m["video_id"]]) for m in order]))
                checked += 1
            else:
                self.assertTrue(any("aviso" in n for n in notes))
        self.assertGreater(checked, 50)

    def test_order_is_deterministic_regardless_of_input_order(self):
        rnd = random.Random(7)
        vids, ms = _scenario(rnd, 8, ["a", "b", "c", "d"])
        base = [m["id"] for m in timeline.smart_order(ms, vids)[0]]
        for _ in range(10):
            shuffled = ms[:]
            rnd.shuffle(shuffled)
            self.assertEqual([m["id"] for m in timeline.smart_order(shuffled, vids)[0]], base)

    def test_opens_with_short_high_energy_hook(self):
        vids = [{"id": i, "author_handle": f"@{i}", "viral_score": 50} for i in "abcd"]
        mk = lambda i, s, d, r: {"id": i, "video_id": i, "score": s, "start": 0, "end": d, "selected": True,
                                 "ranking": {"criteria": {"reacao": r, "retencao": r}}}
        ms = [mk("a", 95, 40, 50), mk("b", 80, 12, 95), mk("c", 82, 60, 95), mk("d", 70, 20, 30)]
        order = [m["id"] for m in timeline.smart_order(ms, vids)[0]]
        self.assertEqual(order[0], "b")   # curto e com mais energia entre os bons
        self.assertEqual(order[-1], "a")  # o melhor fecha

    def test_original_creator_counts_as_the_same_person(self):
        vids = [{"id": "v1", "author_handle": "@fa1", "original_creator": {"name": "alanzoka"}, "viral_score": 1},
                {"id": "v2", "author_handle": "@fa2", "original_creator": {"name": "Alanzoka"}, "viral_score": 1},
                {"id": "v3", "author_handle": "@outro", "viral_score": 1}]
        ms = [{"id": f"m{i}", "video_id": f"v{i}", "score": s, "start": 0, "end": 20, "selected": True}
              for i, s in ((1, 90), (2, 80), (3, 70))]
        order = [m["video_id"] for m in timeline.smart_order(ms, vids)[0]]
        self.assertNotEqual(order.index("v1") - order.index("v2"), 1)
        self.assertNotEqual(order.index("v2") - order.index("v1"), 1)

    def test_unselected_moments_are_ignored(self):
        vids = [{"id": "v", "author_handle": "@a", "viral_score": 1}]
        ms = [{"id": "m1", "video_id": "v", "score": 90, "start": 0, "end": 10, "selected": False}]
        self.assertEqual(timeline.smart_order(ms, vids)[0], [])


class Render(unittest.TestCase):
    def test_short_window_keeps_short_moments_whole(self):
        self.assertEqual(render.short_window({"start": 2.0, "end": 32.0}), (2.0, 30.0))

    def test_short_window_centers_long_moment_on_peak(self):
        self.assertEqual(render.short_window({"start": 0.0, "end": 90.0, "peak_time": 57.5}), (30.0, 60.0))
        self.assertEqual(render.short_window({"start": 0.0, "end": 90.0, "peak_time": 10.0}), (6.0, 60.0))

    def test_filters_choose_layout_by_orientation(self):
        self.assertIn("overlay=(W-w)/2:0", render.compilation_filter({"width": 720, "height": 1280}))
        self.assertIn("pad=1920:1080", render.compilation_filter({"width": 1280, "height": 720}))
        self.assertIn("boxblur", render.short_filter({"width": 1280, "height": 720}))

    def test_silent_video_gets_silence_track_and_no_loudnorm(self):
        args = render.encode_args("s.mp4", 0, 10, False, "fps=30", "o.mp4")
        self.assertIn("anullsrc=r=48000:cl=stereo", args)
        self.assertNotIn("-af", args)

    def test_credit_is_read_from_file_without_expansion(self):
        vf = render.compilation_filter({"width": 2, "height": 1}, credit_file="credits/v.txt")
        self.assertIn("drawtext=textfile=credits/v.txt:expansion=none:", vf)
        self.assertNotIn("text='", vf)


class Contracts(unittest.TestCase):
    def test_missing_and_wrong_fields_are_reported(self):
        errs = check_items("moments", [{"id": "m01", "video_id": "v", "source": "s", "start": "0", "end": 1,
                                        "score": 10, "signals": [], "selected": True}])
        self.assertEqual(errs, ["moments[0].start: tipo str inválido"])

    def test_project_validate_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            save_json(pathlib.Path(d, "discovery.json"), {"videos": [{
                "id": "v", "url": "u", "author_handle": "@a", "viral_score": 1, "approved": True, "rights": "unknown",
                "local_path": "source/v.mp4", "duration_s": 1.0, "width": 2, "height": 2, "has_audio": True}]})
            self.assertTrue(any("não existe" in e for e in Project(d).validate()))

    def test_ytdlp_mapping(self):
        v = _from_ytdlp({"id": 123, "webpage_url": "https://x.com/foo/status/999", "uploader": "Foo",
                         "uploader_id": "foo", "timestamp": 0, "like_count": 5})
        self.assertEqual((v["id"], v["post_id"], v["author_handle"], v["platform"], v["likes"], v["reposts"]),
                         ("123", "999", "@foo", "x", 5, None))


class Rights(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = rights.Ledger(pathlib.Path(self.tmp.name, "permissions.json"))
        self.clip = {"id": "v1", "post_id": "10", "author": "Fã", "author_handle": "@clipador",
                     "original_creator": {"name": "alanzoka"}, "rights": "unknown", "approved": True}
        self.own = {"id": "v2", "post_id": "20", "author_handle": "@jogador", "rights": "unknown", "approved": True}

    def tearDown(self):
        self.tmp.cleanup()

    def test_credit_shows_creator_and_clipper(self):
        self.assertEqual(rights.credit_text(self.clip), "alanzoka | clipe @clipador")
        self.assertEqual(rights.credit_text(self.own), "@jogador")

    def test_credit_drops_emoji_the_font_cannot_draw(self):
        self.assertEqual(rights.credit_text(dict(self.own, author_handle="@gta 😂🔥 ⚡️fã")), "@gta fã")

    def test_creator_must_authorize_not_the_clipper(self):
        self.assertEqual(rights.owner_of(self.clip), "alanzoka")
        self.ledger.set("@clipador", "granted", evidence="https://x.com/clipador/status/1")
        self.assertEqual(self.ledger.status_for(self.clip), "unknown")
        self.ledger.set("alanzoka", "granted", evidence="print.png")
        self.assertEqual(self.ledger.status_for(self.clip), "granted")

    def test_granted_requires_evidence(self):
        with self.assertRaises(ValueError):
            self.ledger.set("@jogador", "granted")

    def test_post_specific_permission_overrides_general(self):
        self.ledger.set("@jogador", "denied")
        self.ledger.set("@jogador", "granted", evidence="dm.png", post_id="20")
        self.assertEqual(self.ledger.status_for(self.own), "granted")
        self.assertEqual(self.ledger.status_for(dict(self.own, post_id="99")), "denied")

    def test_ledger_persists_between_projects(self):
        self.ledger.set("@jogador", "granted", evidence="dm.png")
        again = rights.Ledger(self.ledger.path)
        self.assertEqual(again.status_for(self.own), "granted")

    def test_sync_marks_rights_and_removes_denied(self):
        self.ledger.set("alanzoka", "denied")
        disc = {"videos": [self.clip, self.own]}
        rights.sync_project(disc, self.ledger)
        self.assertEqual((self.clip["rights"], self.clip["approved"]), ("denied", False))
        self.assertEqual(self.own["rights"], "unknown")

    def test_publish_blocked_until_permission_or_explicit_override(self):
        self.assertFalse(rights.publish_check([self.own])["publish_ready"])
        self.assertFalse(rights.publish_check([self.own], {"reason": "  "})["publish_ready"])
        r = rights.publish_check([self.own], {"reason": "uso transformativo, decisão minha"})
        self.assertTrue(r["publish_ready"])
        self.assertEqual(r["override"]["reason"], "uso transformativo, decisão minha")
        self.own["rights"] = "permission_granted"
        r = rights.publish_check([self.own])
        self.assertTrue(r["publish_ready"] and r["override"] is None)

    def test_templates_parse_and_fit_280(self):
        text = pathlib.Path(__file__).resolve().parent.parent.joinpath(
            ".claude/skills/gta-video-discovery/permission-template.md").read_text(encoding="utf-8")
        tpl = rights.parse_templates(text)
        self.assertEqual(set(tpl), {"pt", "en", "es"})
        self.assertEqual(set(tpl["pt"]), {"dm", "reply"})
        msg = rights.fill(tpl["pt"]["dm"], dict(self.own, url="https://x.com/jogador/status/20"), "Canal GTA")
        self.assertNotIn("<", msg)
        self.assertLessEqual(rights.x_length(msg), 280)

    def test_language_guess(self):
        self.assertEqual(rights.guess_lang("puta que pariu esse clipe KKKKK"), "pt")
        self.assertEqual(rights.guess_lang("bro this is insane lmao"), "en")
        self.assertEqual(rights.guess_lang("jajaja pero qué es esto hermano"), "es")


if __name__ == "__main__":
    unittest.main()
