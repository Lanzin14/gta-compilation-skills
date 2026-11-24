"""Testes do ranking inteligente de clipes (gtakit/ranking.py) com medições montadas à mão.

Cenários pedidos: áudio alto constante, grito isolado, piada com preparação longa, reação curta,
clipe sem pico de áudio, clipe com silêncio e clipes duplicados.
"""
import pathlib
import random
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from gtakit import ranking  # noqa: E402

CFG = ranking.load_config()
NO_DEAD = {"silence_start": [], "silence_end": [], "freeze_start": [], "freeze_end": []}


def meas(duration, db=lambda t: -25.0, motion=lambda t: 6.0, has_audio=True, scenes=(), dead=None,
         height=1080, width=1920, yavg=110.0, blur=5.0, seed=1):
    """Medições sintéticas: volume e movimento por janela de 0,5 s, e quadros com 'hash' distintos."""
    n = int(duration * 2)
    rnd = random.Random(seed)
    return {
        "duration_s": float(duration), "width": width, "height": height, "fps": 60.0, "has_audio": has_audio,
        "rms": [(i / 2, db(i / 2)) for i in range(n)] if has_audio else [],
        "scenes": list(scenes), "dead": dead or NO_DEAD,
        "visual": [(i / 2, motion(i / 2), yavg, blur) for i in range(n)],
        "loudness": {"lufs": -18.0, "true_peak_dbfs": -2.0} if has_audio else None,
        "hashes": [rnd.getrandbits(64) for _ in range(n)],
    }


def video(vid, text="", viral=50, **kw):
    return dict({"id": vid, "local_path": f"source/{vid}.mp4", "text": text, "viral_score": viral,
                 "author_handle": f"@{vid}", "url": f"https://x.com/{vid}/status/1"}, **kw)


def rank(videos, measures, transcripts=None, judgments=None, cfg=CFG):
    return ranking.rank(videos, measures, transcripts or {}, judgments or {}, cfg)


def tr(*segs):
    return {"language": "pt", "segments": [{"start": a, "end": b, "text": t} for a, b, t in segs]}


class RequestedScenarios(unittest.TestCase):
    def test_constant_loud_audio_is_not_discarded_and_stays_whole(self):
        # O caso real do @swordarling: áudio alto o tempo todo, nenhum "pico", clipe mais viral.
        v = video("alto", text="puta que pariu esse clipe, ri demais", viral=100)
        m = rank([v], {"alto": meas(89, db=lambda t: -18.0)})
        self.assertEqual(len(m), 1)
        self.assertTrue(m[0]["selected"], m[0]["ranking"]["selection_reason"])
        self.assertEqual((m[0]["start"], m[0]["end"]), (0.0, 89.0))  # ≤ 90 s: inteiro
        self.assertLess(m[0]["ranking"]["criteria"]["reacao"], 30)   # volume não mostra reação...
        self.assertTrue(any("sem variação" in a for a in m[0]["ranking"]["alerts"]))  # ...e isso é explicado
        self.assertGreaterEqual(m[0]["ranking"]["criteria"]["humor"], 60)  # humor veio do texto do post

    def test_isolated_scream(self):
        v = video("grito")
        m = rank([v], {"grito": meas(20, db=lambda t: -12.0 if 12 <= t < 13 else -45.0)})[0]
        self.assertGreaterEqual(m["ranking"]["criteria"]["reacao"], 60)
        self.assertTrue(12.0 <= m["peak_time"] < 13.0)
        self.assertIn("audio_peak", m["signals"])

    def test_long_setup_joke_keeps_the_whole_setup(self):
        # Vídeo de 2 min; a conversa que prepara a piada começa aos 40 s, o grito é aos 60 s, a risada aos 61 s.
        v = video("piada")
        segs = tr((40.0, 46.0, "então mano, olha o que eu vou fazer"), (46.5, 52.0, "vou subir nessa torre aqui"),
                  (52.5, 59.5, "se eu pular eu caio na água, confia"), (60.0, 61.0, "AAAAAA"),
                  (61.2, 64.5, "kkkkkkk não acredito"))
        m = rank([v], {"piada": meas(120, db=lambda t: -10.0 if 60 <= t < 61 else -30.0)}, {"piada": segs})
        best = max(m, key=lambda x: x["ranking"]["final"])
        self.assertLessEqual(best["start"], 40.0)  # inclui toda a preparação contínua
        self.assertGreaterEqual(best["end"], 64.5)  # inclui a risada inteira
        self.assertFalse(any("interrompe uma fala" in a for a in best["ranking"]["alerts"]))
        self.assertGreater(best["ranking"]["criteria"]["humor"], 50)

    def test_short_reaction_clip_is_kept_whole_with_alert(self):
        v = video("curto", viral=80)
        m = rank([v], {"curto": meas(6, db=lambda t: -10.0 if 3 <= t < 4 else -35.0)})[0]
        self.assertEqual((m["start"], m["end"]), (0.0, 6.0))
        self.assertTrue(any("muito curto" in a for a in m["ranking"]["alerts"]))

    def test_clip_without_audio_peak_is_judged_by_content(self):
        # Sem pico de volume, mas a fala mostra risada: não pode ser descartado por falta de pico.
        v = video("semPico", viral=40)
        m = rank([v], {"semPico": meas(30, db=lambda t: -28.0)},
                 {"semPico": tr((5.0, 8.0, "mano kkkkk"), (10.0, 13.0, "hahaha que isso"), (20.0, 22.0, "kkkk"))})[0]
        self.assertEqual(m["peaks"], [])
        self.assertTrue(m["selected"], m["ranking"]["selection_reason"])
        self.assertGreaterEqual(m["ranking"]["criteria"]["humor"], 70)

    def test_silent_clip_does_not_break_and_is_flagged(self):
        v = video("mudo")
        m = rank([v], {"mudo": meas(15, has_audio=False, motion=lambda t: 40.0 if 7 <= t < 8 else 3.0)})[0]
        self.assertTrue(7.0 <= m["peak_time"] < 8.0)  # ação vem do movimento
        self.assertTrue(any("sem áudio" in a for a in m["ranking"]["alerts"]))
        v2 = video("quieto")
        m2 = rank([v2], {"quieto": meas(20, db=lambda t: -58.0 if t < 17 else -20.0)})[0]
        self.assertTrue(any("silêncio" in a for a in m2["ranking"]["alerts"]))

    def test_duplicates_keep_only_the_best(self):
        same = meas(30, db=lambda t: -15.0 if 10 <= t < 11 else -30.0 + (t % 3), seed=7)
        copy = dict(same, hashes=[h ^ 1 for h in same["hashes"]])  # reupload: 1 bit diferente por quadro
        a, b = video("orig", viral=90), video("repost", viral=30)
        m = {x["video_id"]: x for x in rank([a, b], {"orig": same, "repost": copy})}
        self.assertTrue(m["orig"]["selected"])
        self.assertFalse(m["repost"]["selected"])
        self.assertEqual(m["repost"]["ranking"]["duplicate_of"], "orig")


class Behaviour(unittest.TestCase):
    def test_virality_is_separate_from_content(self):
        viral_bad = video("viral", viral=100)
        good_unknown = video("bom", text="kkkkk ri demais", viral=10)
        m = {x["video_id"]: x for x in rank(
            [viral_bad, good_unknown],
            {"viral": meas(30, db=lambda t: -60.0, height=360, width=640, yavg=20.0, seed=2),
             "bom": meas(30, db=lambda t: -12.0 if 14 <= t < 15 else -30.0, seed=3)})}
        self.assertEqual(m["viral"]["ranking"]["criteria"]["viralidade"], 100)
        self.assertLess(m["viral"]["ranking"]["criteria"]["qualidade"], m["bom"]["ranking"]["criteria"]["qualidade"])
        self.assertGreater(m["bom"]["ranking"]["final"], m["viral"]["ranking"]["final"])

    def test_repetitive_clip_is_flagged(self):
        frames = [11, 22, 33, 44, 55, 66]
        mm = meas(30)
        mm["hashes"] = [frames[i % 6] for i in range(60)]  # a mesma sequência de 3 s em loop
        m = rank([video("loop")], {"loop": mm})[0]
        self.assertTrue(any("repetitivo" in a for a in m["ranking"]["alerts"]))

    def test_weights_are_configurable(self):
        v = video("x", viral=100)
        mm = {"x": meas(20, db=lambda t: -45.0)}
        only_viral = ranking.clone_config(CFG, weights={k: 0.0 for k in ranking.CRITERIA})
        only_viral["weights"]["viralidade"] = 1.0
        self.assertEqual(rank([v], mm, cfg=only_viral)[0]["ranking"]["final"], 100.0)

    def test_claude_judgment_needs_a_reason(self):
        v = video("j")
        mm = {"j": meas(20)}
        no_reason = rank([v], mm, judgments={"j": {"humor": {"score": 99}}})[0]
        with_reason = rank([v], mm, judgments={"j": {"humor": {"score": 99, "reason": "a física do carro é absurda"}}})[0]
        self.assertNotEqual(no_reason["ranking"]["criteria"]["humor"], 99)
        self.assertEqual(with_reason["ranking"]["criteria"]["humor"], 99)
        self.assertEqual(with_reason["ranking"]["humor_source"], "avaliação do Claude")

    def test_cut_never_starts_inside_speech(self):
        segs = tr((95.0, 105.0, "e aí galera, olha só essa fuga da polícia"), (105.5, 107.0, "caralho"))
        m = rank([video("fala")], {"fala": meas(200, db=lambda t: -10.0 if 106 <= t < 107 else -30.0)}, {"fala": segs})
        best = max(m, key=lambda x: x["ranking"]["final"])
        self.assertLessEqual(best["start"], 95.0)

    def test_every_moment_has_report_fields(self):
        for x in rank([video("r", text="kkkk")], {"r": meas(40)}):
            r = x["ranking"]
            self.assertEqual(set(r["criteria"]), set(ranking.CRITERIA))
            self.assertTrue(r["justification"])
            self.assertIn("duration_s", r["recommended"])
            self.assertTrue(r["selection_reason"])
            self.assertIsNotNone(x["peak_time"])

    def test_report_markdown_has_one_row_per_moment(self):
        v = video("md")
        ms = rank([v], {"md": meas(20)})
        for i, x in enumerate(ms, 1):
            x["id"] = f"m{i:02d}"
        md = ranking.report_markdown(ms, {"md": v})
        self.assertIn("| 1 | @md |", md)
        self.assertIn("URL original: https://x.com/md/status/1", md)


if __name__ == "__main__":
    unittest.main()
