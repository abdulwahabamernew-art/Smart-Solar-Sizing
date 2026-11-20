import json
import unittest
from pathlib import Path
from solar.engine import *


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((Path(__file__).parents[1] / 'data/config.json').read_text(encoding='utf-8'))['appliances']

    def test_duals_and_arabic_digits(self):
        p = extract_appliances('مكيفين و ثلاجتين و ٣ شاشات', self.catalog)
        self.assertEqual([x['quantity'] for x in p['items']], [2, 2, 3])
        self.assertFalse(p['unresolved'])

    def test_units_not_quantity(self):
        p = extract_appliances('ثلاجة 150 واط لمدة 8 ساعات', self.catalog)['items'][0]
        self.assertEqual((p['quantity'], p['watts'], p['hours']), (1, 150, 8))

    def test_kw_override(self):
        p = extract_appliances('٢ مكيف 1.2 كيلوواط 5 ساعات', self.catalog)['items'][0]
        self.assertEqual((p['quantity'], p['watts'], p['hours']), (2, 1200, 5))

    def test_distinct_longest_alias(self):
        p = extract_appliances('ثلاجة عرض و كشاف و كمبيوتر', self.catalog)
        self.assertEqual([x['appliance'] for x in p['items']], ['ثلاجة عرض', 'كشاف', 'كمبيوتر'])
        self.assertEqual(len(p['items']), 3)

    def test_unknown_is_reported(self):
        p = extract_appliances('جهاز مجهول 500 واط', self.catalog)
        self.assertFalse(p['items'])
        self.assertTrue(p['unresolved'])

    def test_unlabelled_number_requires_review(self):
        p = extract_appliances('ثلاجة 150', self.catalog)
        self.assertEqual(p['items'][0]['quantity'], 1)
        self.assertTrue(p['unresolved'])

    def test_energy_and_battery(self):
        r = size_loads([dict(quantity=2, watts=100, hours=5)], 5, 0.8, 600)
        self.assertEqual(r['daily_energy_wh'], 1000)
        self.assertEqual(r['required_pv_w'], 250)
        self.assertAlmostEqual(r['battery_nominal_wh'], 600 / (0.8 * 0.95))

    def test_no_implicit_full_day_battery(self):
        r = size_loads([dict(quantity=1, watts=100, hours=5)], 5)
        self.assertIsNone(r['battery_nominal_wh'])

    def test_well_energy_and_hours(self):
        r = size_well(100, 100, 5, 5, 0.5, 0.8, 1, 0.8)
        self.assertAlmostEqual(r['hydraulic_energy_kwh_day'], 27.25)
        self.assertAlmostEqual(r['required_pv_w'], 17031.25)
        other = size_well(100, 100, 5, 10, 0.5, 0.8, 1, 0.8)
        self.assertEqual(r['required_pv_w'], other['required_pv_w'])
        self.assertAlmostEqual(r['estimated_shaft_kw'], 2 * other['estimated_shaft_kw'])

    def test_existing_pump_hours(self):
        a = size_existing_pump(10, 4, 5)
        b = size_existing_pump(10, 8, 5)
        self.assertAlmostEqual(b['required_pv_w'], 2 * a['required_pv_w'])

    def test_invalid_inputs(self):
        for bad in [0, -1, float('nan'), float('inf')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                size_well(100, 100, bad, 5)
        with self.assertRaises(ValueError):
            size_loads([], 5)
        with self.assertRaises(ValueError):
            size_well(100, 100, 5, 25)

    def specs(self):
        return Panel(710, 48.6, 40.65, 19, 17.5, -0.0025, -0.0029), PVInput(850, 480, 800, 40, 50, 2, 2, 50000)

    def test_array_never_undersizes(self):
        p, inv = self.specs()
        for watts in [1, 10000, 20000, 25753, 30000, 45000]:
            with self.subTest(watts=watts):
                r = design_array(watts, p, inv, 0, 58)
                self.assertGreaterEqual(r['actual_pv_w'], watts)
                self.assertLessEqual(r['actual_pv_w'], inv.max_pv_power_w)
                self.assertLessEqual(r['string_voc_max_v'], inv.max_dc_v)
                self.assertGreaterEqual(r['string_vmp_min_v'], inv.mppt_min_v)
                self.assertLessEqual(r['string_vmp_max_v'], inv.mppt_max_v)
                self.assertEqual(sum(r['strings_by_mppt']), r['parallel_strings'])
                for n in r['strings_by_mppt']:
                    self.assertLessEqual(n * p.imp_a, inv.max_operating_current_a_per_mppt)
                    self.assertLessEqual(n * p.isc_a * 1.25, inv.max_short_circuit_current_a_per_mppt)

    def test_array_rejects_infeasible(self):
        p, inv = self.specs()
        with self.assertRaises(ValueError):
            design_array(100000, p, inv, 0, 58)
        with self.assertRaises(ValueError):
            design_array(25000, p, PVInput(850, 480, 800, 10, 15, 2, 2, 50000), 0, 58)

    def test_hard_capacity_and_ac_dc_separation(self):
        base = dict(category='inverter', ac_phase=3, ac_voltage_v=380, price_usd=1000, stock_qty=1, battery_min_v=40, battery_max_v=60, verification_status='verified', datasheet_source='synthetic test fixture')
        rows = [dict(base, id='small', continuous_w=950), dict(base, id='ok', continuous_w=1100), dict(base, id='wrong_ac', continuous_w=1200, ac_voltage_v=220)]
        r = recommend_inverters(rows, 1000, 3, 380, 48)
        self.assertEqual([x['id'] for x in r['candidates']], ['ok'])
        r = recommend_inverters(rows, 1000, 3, 380, 400)
        self.assertFalse(r['candidates'])

    def test_missing_surge_rejects(self):
        row = dict(id='x', category='inverter', ac_phase=1, ac_voltage_v=220, continuous_w=2000, price_usd=100, stock_qty=1, verification_status='verified', datasheet_source='synthetic test fixture')
        self.assertFalse(recommend_inverters([row], 1000, 1, 220, required_surge_va=3000, required_surge_seconds=5)['candidates'])

    def test_unverified_inventory_rejected(self):
        row = dict(id='x', category='inverter', ac_phase=1, ac_voltage_v=220, continuous_w=2000, price_usd=100, stock_qty=1)
        self.assertFalse(recommend_inverters([row], 1000, 1, 220)['candidates'])

    def test_industrial_start_includes_other_loads(self):
        r = size_motor_load(10, 5, 8, 6, starting_current_factor=6, starting_duration_seconds=3)
        self.assertAlmostEqual(r['preliminary_starting_va'], (10 * 0.746 / 0.88 / 0.85 * 6 + 5) * 1000)
        self.assertEqual(r['starting_duration_seconds'], 3)
        self.assertIsNone(size_motor_load(10, 5, 8, 6)['preliminary_starting_va'])


if __name__ == '__main__':
    unittest.main()
