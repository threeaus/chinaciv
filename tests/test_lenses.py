import unittest

from pipeline.build.lenses import make_lenses


class LensTests(unittest.TestCase):
    def test_city_and_state_values_do_not_cross_boundaries_or_use_census_as_denominator(self):
        world = {
            "owner": [0, 0, 0, 1, -1],
            "county": [0, 1, -1, 0, 0],
            "counties": [{"geoid": "010101"}, {"geoid": "010201"}],
            "states": [{"fips": "01"}, {"fips": "02"}],
        }
        cities = [
            {"id": "010100", "counties": ["010101"], "states": ["01"], "gdp": 1000,
             "gdp_year": 2023, "population": 10, "population_year": 2023},
            {"id": "010200", "counties": ["010201"], "states": ["01"], "gdp": 2500,
             "gdp_year": 2023, "pop_census_2020": 20},
        ]
        states = [{"fips": "01", "growth": -0.02, "growth_years": [2020, 2023]}]
        stats = {"cities": {"010100": {"urban_pct": 75, "income_pc": 42000}}, "provinces": {"01": {"urban_pct": 100}}}
        lenses = {lens["id"]: lens for lens in make_lenses(world, cities, states, stats)["lenses"]}
        self.assertEqual(lenses["city-gdp-per-capita"]["values"], [100, None, None, None, None])
        self.assertEqual(lenses["state-growth"]["values"], [-0.02, -0.02, -0.02, None, None])
        self.assertEqual(lenses["city-urbanization"]["values"], [0.75, None, None, None, None])
        self.assertEqual(lenses["state-urbanization"]["values"], [1, 1, 1, None, None])
        self.assertEqual(lenses["city-income"]["values"], [42000, None, None, None, None])
