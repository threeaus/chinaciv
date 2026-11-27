import unittest

from pipeline.build.counties import county_rows


class CountyGeometryTests(unittest.TestCase):
    def test_county_geometry_includes_districts_without_a_hex_sample(self):
        district = {"adcode": "110101", "name": "东城区", "prefecture": "110000", "province": "11",
                    "seat": [2, 3], "rings": [[[1, 2], [2, 3], [3, 2], [1, 2]]]}
        rows = county_rows([district], {}, lambda x, y: (x + 1, y + 1))
        self.assertEqual(rows[0]["id"], "110101")
        self.assertEqual(rows[0]["seat"], [3, 4])
        self.assertEqual(rows[0]["bounds"], [2, 3, 4, 4])
        self.assertEqual(rows[0]["cells"], 0)
