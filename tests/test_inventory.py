import unittest
from pathlib import Path
from solar.inventory import *


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = Path(__file__).parents[1] / 'data'
        cls.snapshots = [import_snapshot(p) for p in sorted(folder.glob('legacy_inventory_*.json'))]
        cls.rows = [r for s in cls.snapshots for r in s['records']]
        cls.source = cls.snapshots[1]['source_id']

    def test_all_sources_without_totals(self):
        self.assertEqual([len(s['records']) for s in self.snapshots], [23, 26, 36])
        self.assertEqual(len(self.rows), 85)
        self.assertEqual(len({r['record_id'] for r in self.rows}), 85)

    def test_raw_fields_and_source_retained(self):
        row = self.rows[0]
        self.assertEqual(row['legacy_item_id'], row['raw_fields']['Item_ID'])
        self.assertEqual(row['source_row'], 7)
        self.assertIn(row['source_id'], row['source_url'])

    def test_battery_is_wh_not_w(self):
        battery = next(r for r in self.snapshots[0]['records'] if r['legacy_item_id'] == 'BAT-01')
        self.assertEqual((battery['capacity_value'], battery['capacity_unit']), (1800, 'Wh'))
        self.assertIsNone(battery['declared_ac_phase'])

    def test_no_guessed_ac_or_battery_range(self):
        for row in self.rows:
            self.assertIsNone(row['ac_voltage_v'])
            self.assertIsNone(row['battery_min_v'])
            self.assertFalse(row['engineering_eligible'])

    def test_panel_vmp_from_correct_column(self):
        p = next(r for r in self.snapshots[0]['records'] if r['legacy_item_id'] == 'PAN-05')
        self.assertEqual((p['vmp_v'], p['voc_v']), (40.6, 48.7))

    def test_audit_conflicts_no_stock_sum(self):
        audit = audit_snapshots(self.snapshots)
        self.assertEqual(audit['engineering_eligible_records'], 0)
        self.assertTrue(audit['exact_model_conflicts'])
        self.assertEqual(audit['total_records'], 85)

    def test_draft_one_source_and_stock_capacity(self):
        draft = build_commercial_draft(self.rows, self.source, 5303.23, 3712.5)
        self.assertFalse(draft['is_final'])
        self.assertEqual(len(draft['lines']), 2)
        by_id = {r['record_id']: r for r in self.rows}
        for line in draft['lines']:
            r = by_id[line['record_id']]
            self.assertEqual(r['source_id'], self.source)
            self.assertLessEqual(line['quantity'], r['stock_qty'])
            if r['category'] == 'panel':
                self.assertGreaterEqual(line['quantity'] * r['capacity_value'], 5303.23)
            else:
                self.assertGreaterEqual(r['capacity_value'], 3712.5)
                self.assertEqual(line['quantity'], 1)
        self.assertEqual(Decimal(draft['listed_items_subtotal_usd']), sum(Decimal(x['subtotal_usd']) for x in draft['lines']))

    def test_no_implicit_parallel_inverters(self):
        d = build_commercial_draft(self.rows, self.source, 10000, 1000000)
        self.assertFalse(any(x['category'] == 'inverter' for x in d['lines']))
        self.assertTrue(d['blocked_items'])

    def test_battery_dod_and_nominal_bus(self):
        d = build_commercial_draft(self.rows, self.source, 6000, 4000, night_energy_wh=6000)
        by_id = {r['record_id']: r for r in self.rows}
        battery = next(x for x in d['lines'] if x['category'] == 'battery')
        row = by_id[battery['record_id']]
        self.assertEqual(row['legacy_voltage_value'], 48)
        self.assertGreaterEqual(row['capacity_value'] * row['declared_dod'] * 0.95 * battery['quantity'], 6000)

    def test_exchange_rates_explicit(self):
        d = build_commercial_draft(self.rows, self.source, 6000, 4000, fx_rates={'TEST': 2}, fx_as_of='user-entered-example')
        self.assertEqual(Decimal(d['converted_subtotals']['TEST']), Decimal(d['listed_items_subtotal_usd']) * 2)
        with self.assertRaises(ValueError):
            build_commercial_draft(self.rows, self.source, 6000, 4000, fx_rates={'TEST': 2})

    def test_invalid_request(self):
        for bad in (0, -1, float('nan'), float('inf')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_commercial_draft(self.rows, self.source, bad, 4000)
        with self.assertRaises(ValueError):
            build_commercial_draft(self.rows, 'missing-source', 5000, 4000)

    def test_currency_rounding(self):
        self.assertEqual(money('1.005'), '1.01')


if __name__ == '__main__':
    unittest.main()
