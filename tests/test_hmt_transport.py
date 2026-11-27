import unittest

from pipeline.build.infrastructure import add_hmt_sites


class Location:
    world = {"counties": []}
    cities = {}

    def place(self, *args, rings):
        return (100, 200, 10)

    def county_at(self, *args):
        return None

    def city_of(self, county):
        return None

    def province_of(self, county, cell, province):
        return province


class TransportSupplementTests(unittest.TestCase):
    def test_port_preserves_comparable_and_container_only_measures(self):
        doc = {"airports": [], "ports": []}
        ports = [{"id": "MO", "name": "澳门港", "state": "82", "year": 2025, "lon": 113.5, "lat": 22.2,
                  "cargo_t": None, "container_cargo_t": 187090, "teu": 120205,
                  "source": "https://example.org", "publisher": "统计局"}]
        add_hmt_sites(doc, Location(), {"ports": ports}, [])
        add_hmt_sites(doc, Location(), {"ports": ports}, [])
        self.assertEqual(len(doc["ports"]), 1)
        self.assertIsNone(doc["ports"][0]["rank"])
        self.assertIsNone(doc["ports"][0]["cargo_t"])
        self.assertEqual(doc["ports"][0]["container_cargo_t"], 187090)
