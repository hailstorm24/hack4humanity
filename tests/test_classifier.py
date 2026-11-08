"""Classifier stub: rule coverage, demo phrases, matching and hooks.

See docs/classifier-stub-plan.md (Stage 3).

    python3 -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "stubs"))

import classifier  # noqa: E402
from common import HttpError  # noqa: E402

NEUTRAL = [
    "Сегодня хорошая погода, пойдём гулять.",
    "Где купить хлеб рядом с метро?",
    "Сколько стоит билет на поезд до Казани?",
    "Мама испекла пирог с яблоками.",
    "Спасибо за донаты на стриме!",
    "Встреча перенесена на четверг.",
    "Котёнок спит на подоконнике.",
    "Не забудь купить молоко.",
    "What time is the meeting tomorrow?",
    "I donated to the animal shelter.",
    "The train was late again this morning.",
    "Can you send me the recipe?",
    "Happy birthday, have a great day!",
    "Our team won the football match.",
    "Please water the plants while I'm away.",
]


def top(text):
    labels = classifier.score_text(text)
    return labels[0] if labels else None


class CoverageTest(unittest.TestCase):
    def test_every_taxonomy_label_has_a_rule(self):
        have = {(r["narrative"], r["subnarrative"]) for r in classifier.RULES}
        for n in classifier.TAXONOMY["narratives"]:
            for s in n["subnarratives"] or [None]:
                self.assertIn((n["name"], s), have)

    def test_model_version(self):
        self.assertEqual(classifier.MODEL_VERSION, "stub-keywords-0.2")


class DemoTest(unittest.TestCase):
    def test_each_demo_tops_its_own_label(self):
        for r in classifier.RULES:
            for lang, text in r.get("demo", {}).items():
                with self.subTest(label=r["subnarrative"] or r["narrative"], lang=lang):
                    got = top(text)
                    self.assertIsNotNone(got, text)
                    self.assertEqual((got["narrative"], got["subnarrative"]),
                                     (r["narrative"], r["subnarrative"]), text)
                    self.assertGreaterEqual(got["score"], 0.7)


class MatchingTest(unittest.TestCase):
    def test_neutral_text_has_no_labels(self):
        for text in NEUTRAL:
            with self.subTest(text=text):
                self.assertEqual(classifier.score_text(text), [])

    def test_keywords_match_at_word_start_only(self):
        self.assertEqual(classifier.score_text("донатов много"), [])
        self.assertEqual(top("Это провокационный шаг")["subnarrative"], "The West are the aggressors")

    def test_yo_is_e(self):
        self.assertEqual(top("Европа замёрзнет")["subnarrative"],
                         "Sanctions imposed by Western countries will backfire")

    def test_case_and_whitespace(self):
        self.assertEqual(top("НАЦИСТЫ  \n в Киеве")["subnarrative"], "Ukraine is associated with nazism")

    def test_catch_all_alone(self):
        self.assertEqual(classifier.score_text("Европа"),
                         [{"narrative": "Discrediting the West, Diplomacy", "subnarrative": None, "score": 0.41}])

    def test_extra_hits_add_bonus(self):
        self.assertEqual(top("нацисты")["score"], 0.86)
        self.assertEqual(top("нацисты и фашисты")["score"], 0.89)
        self.assertEqual(top("нацисты, фашисты, бандеровцы, азовцы")["score"], 0.95)

    def test_several_labels_sorted(self):
        labels = classifier.score_text("Бандеровцы готовят ядерную провокацию")
        self.assertEqual([l["subnarrative"] for l in labels],
                         ["The West are the aggressors", "Ukraine is associated with nazism",
                          "There is a real possibility that nuclear weapons will be employed"])


class RuleFileTest(unittest.TestCase):
    def _load(self, rules):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"model_version": "t", "rules": rules}, f)
        self.addCleanup(os.unlink, f.name)
        return classifier.load_rules(f.name)

    def rule(self, **kw):
        r = {"narrative": "Discrediting Ukraine", "subnarrative": "Ukraine is associated with nazism",
             "score": 0.8, "keywords": {"ru": ["нацист"], "en": ["nazi"]},
             "demo": {"ru": "нацисты", "en": "nazis"}}
        return {**r, **kw}

    def test_valid(self):
        self.assertEqual(len(self._load([self.rule()])[1]), 1)

    def test_unknown_label(self):
        with self.assertRaisesRegex(ValueError, "not in taxonomy"):
            self._load([self.rule(subnarrative="Made up")])

    def test_duplicate_keyword(self):
        with self.assertRaisesRegex(ValueError, "already used"):
            self._load([self.rule(), self.rule(subnarrative="Ukraine is a puppet of the West",
                                               keywords={"ru": ["Нацист"]})])

    def test_missing_demo(self):
        with self.assertRaisesRegex(ValueError, "demo"):
            self._load([self.rule(demo={"ru": "нацисты"})])

    def test_catch_all_needs_no_demo(self):
        r = self.rule(score=0.4)
        del r["demo"]
        self.assertEqual(len(self._load([r])[1]), 1)


class HooksTest(unittest.TestCase):
    def test_fail(self):
        with self.assertRaises(HttpError) as cm:
            classifier.classify(None, None, {"text": "#fail"})
        self.assertEqual(cm.exception.status, 503)

    def test_slow(self):
        with mock.patch.object(classifier.time, "sleep") as sleep:
            status, body = classifier.classify(None, None, {"text": "#slow нацисты"})
        sleep.assert_called_once_with(12)
        self.assertEqual((status, body["labels"][0]["score"], body["model_version"]),
                         (200, 0.86, "stub-keywords-0.2"))


if __name__ == "__main__":
    unittest.main()
