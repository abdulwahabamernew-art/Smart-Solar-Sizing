import copy
import json
import unittest
from pathlib import Path
from solar.compatibility import screen_array, enumerate_arrays


class CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = json.loads((Path(__file__).parents[1] / 'data/manufacturer_profiles.json').read_text(encoding='utf-8'))
        cls.p = cls.profiles['panel']
        cls.g, cls.d = cls.profiles['inverters']

    def screen(self, inverter=None, series=5, strings=None, **kwargs):
        options = dict(required_pv_w=5303.23, min_cell_c=0, max_cell_c=70)
        options.update(kwargs)
        return screen_array(self.p, inverter or self.d, series, strings if strings is not None else [1, 1], **options)

    def test_growatt_per_string_constraint(self):
        r = self.screen(self.g, 7, [1], required_pv_w=4000, min_cell_c=25, max_cell_c=25)
        self.assertIn('mppt_1_per_string_current', r['failed_checks'])
        self.assertNotIn('mppt_1_operating_current', r['failed_checks'])

    def test_two_mppt_not_two_parallel_on_one(self):
        separate = self.screen(strings=[1, 1])
        together = self.screen(strings=[2, 0])
        self.assertEqual(separate['status'], 'conditional')
        self.assertIn('mppt_1_operating_current', together['failed_checks'])

    def test_missing_vmp_never_fabricated(self):
        r = self.screen()
        self.assertIsNone(r['string_vmp_range_v'])
        state = next(c['state'] for c in r['checks'] if c['check'] == 'thermal_mppt')
        self.assertEqual(state, 'pending')
        self.assertIsNone(self.p['beta_vmp_per_c'])

    def test_assumed_coefficient_remains_conditional(self):
        r = self.screen(assumed_beta_vmp_per_c=-0.003)
        state = next(c['state'] for c in r['checks'] if c['check'] == 'thermal_mppt')
        self.assertEqual(state, 'assumed_pass')
        self.assertEqual(r['status'], 'conditional')
        self.assertFalse(r['installation_approved'])
        self.assertAlmostEqual(r['string_vmp_range_v'][0], 190.3865)

    def test_site_altitude_rejects(self):
        r = self.screen(site_altitude_m=2300)
        self.assertIn('site_altitude', r['failed_checks'])

    def test_derating_is_pending(self):
        r = self.screen(site_max_ambient_c=50)
        self.assertEqual(next(c['state'] for c in r['checks'] if c['check'] == 'ambient_derating'), 'pending')

    def test_hot_environment_rejects(self):
        self.assertIn('ambient_derating', self.screen(site_max_ambient_c=65)['failed_checks'])

    def test_voltage_limit_and_energy_reject(self):
        self.assertIn('max_dc_voltage', self.screen(series=10)['failed_checks'])
        self.assertIn('energy_capacity', self.screen(series=3)['failed_checks'])

    def test_enumeration_selects_ten_panels_on_separate_mppts(self):
        result = enumerate_arrays(self.p, self.d, 5303.23, min_cell_c=0, max_cell_c=70)
        first = result['candidates'][0]
        self.assertEqual((first['panels'], first['series'], first['strings_by_mppt']), (10, 5, [1, 1]))
        self.assertTrue(all(r['array_stc_w'] >= 5303.23 for r in result['candidates']))
        self.assertTrue(all(not r['installation_approved'] for r in result['candidates']))

    def test_no_growatt_candidates(self):
        result = enumerate_arrays(self.p, self.g, 5303.23, min_cell_c=0, max_cell_c=70)
        self.assertFalse(result['candidates'])
        self.assertGreater(result['rejected_candidate_count'], 0)

    def test_datasheet_revisions_remain_distinct(self):
        self.assertEqual(self.d['max_isc_a_per_mppt'], [34, 34])
        self.assertIsNone(self.g['max_isc_a_per_mppt'])
        self.assertIn('2509', self.g['source_url'])
        self.assertIn('240802', self.d['source_url'])

    def test_invalid_conditions(self):
        for kwargs in [dict(required_pv_w=float('nan')), dict(min_cell_c=80, max_cell_c=70), dict(bifacial_current_gain=-1), dict(irradiance_current_factor=0.5)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.screen(**kwargs)
        with self.assertRaises(ValueError):
            self.screen(strings=[1])
        with self.assertRaises(ValueError):
            self.screen(strings=[-1, 1])


if __name__ == '__main__':
    unittest.main()
