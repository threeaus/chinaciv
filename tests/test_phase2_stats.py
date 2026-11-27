import unittest

from pipeline.build.phase2_stats import apply_population, employment_yields, apply_taiwan_gdp


class SupplementTests(unittest.TestCase):
    def test_population_fills_only_missing_value_and_scope_changes_suppress_growth(self):
        row = {"population": None, "pop_census_2020": 100, "growth": None}
        record = {"population": 110, "source": "https://example.org/statistics"}
        apply_population(row, record, comparable=False)
        self.assertEqual(row["population"], 110)
        self.assertEqual(row["population_year"], 2023)
        self.assertIsNone(row["growth"])
        self.assertEqual(row["population_source"], record["source"])
        apply_population(row, {**record, "population": 105})
        self.assertEqual(row["population"], 110)

    def test_employment_unknown_component_is_not_zero(self):
        self.assertEqual(employment_yields({"I": 41, "M": 0, "R": 12}), {"science": 41, "culture": 12})
        self.assertEqual(employment_yields({"M": 9}), {"science": None, "culture": None})

    def test_taiwan_nominal_gdp_preserves_original_unit(self):
        row = {"yields": {"gold": None}}
        apply_taiwan_gdp(row)
        self.assertEqual(row["gdp_local"], 23_598_348_000_000)
        self.assertEqual(row["gdp"], round(row["gdp_local"] / 4.3973))
        self.assertEqual(row["yields"]["gold"], row["gdp"])
