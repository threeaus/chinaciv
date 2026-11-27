import unittest

from pipeline.build.history import make_rail_history


class RailHistoryTests(unittest.TestCase):
    def test_unknown_and_conventional_links_are_excluded_and_shared_sources_retained(self):
        lines = [[1, 2, 0, "有日期"], [2, 3, 0, "未知"], [3, 4, 1, "有日期"], [4, 5, 0, "2026线"]]
        out = make_rail_history(lines, {"有日期": [2023, "source"], "2026线": [2026, "source"]})
        self.assertEqual(out, [[1, 2, 2023, "有日期", "source"]])
