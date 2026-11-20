"""Lossless legacy import and commercial estimates, separate from engineering approval."""
import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def number(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace('$', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def category(raw):
    raw = str(raw).lower()
    if 'panel' in raw:
        return 'panel'
    if 'battery' in raw:
        return 'battery'
    if 'vfd' in raw:
        return 'pump_vfd'
    if 'inverter' in raw:
        return 'inverter'
    if 'combiner' in raw or 'protection' in raw:
        return 'protection'
    if 'mounting' in raw:
        return 'mounting'
    return 'other'


def import_snapshot(path):
    source = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = source['values']
    header_index = next(i for i, row in enumerate(rows) if row and row[0] == 'Item_ID')
    headers = rows[header_index]
    records, skipped = [], []
    for offset, values in enumerate(rows[header_index + 1:], header_index + 2):
        if not values or not values[0] or values[0] == 'Total':
            skipped.append(offset)
            continue
        raw = dict(zip(headers, values))
        kind = category(raw.get('Category', ''))
        declared_unit = raw.get('Capacity_Unit')
        inferred_unit = 'Wh' if kind == 'battery' else ('W' if kind in ('panel', 'inverter', 'pump_vfd') else None)
        capacity = number(raw.get('Capacity_Value', raw.get('Power_W')))
        raw_phase = str(raw.get('Phase', ''))
        phase = {'1': 1, '3': 3, '1-Phase': 1, '3-Phase': 3}.get(raw_phase) if kind in ('inverter', 'pump_vfd') else None
        price, stock = number(raw.get('Price_USD')), number(raw.get('Stock_Qty'))
        issues = ['manufacturer_ratings_unverified', 'price_and_stock_not_live']
        if inferred_unit and declared_unit not in (None, inferred_unit):
            issues.append('capacity_unit_mismatch')
        if not capacity or capacity <= 0:
            issues.append('invalid_capacity')
        if price is None or price <= 0:
            issues.append('invalid_price')
        if stock is None or stock < 0 or stock != int(stock):
            issues.append('invalid_stock')
        if kind in ('inverter', 'pump_vfd'):
            issues += ['ac_voltage_unverified', 'battery_voltage_range_unverified', 'surge_ratings_missing', 'pv_current_limits_missing']
        elif kind == 'panel':
            issues += ['panel_currents_missing', 'temperature_coefficients_missing']
        elif kind == 'battery':
            issues += ['battery_power_and_bms_compatibility_unverified']
        record = dict(record_id=f"{source['source_id']}:{raw['Item_ID']}",
                      source_id=source['source_id'], source_row=offset,
                      source_url=f"https://docs.google.com/spreadsheets/d/{source['source_id']}/edit",
                      legacy_item_id=raw['Item_ID'], category=kind, brand=raw.get('Brand'), model=raw.get('Model'),
                      capacity_value=capacity, capacity_unit=declared_unit or inferred_unit,
                      declared_ac_phase=phase, ac_voltage_v=None, battery_min_v=None, battery_max_v=None,
                      legacy_voltage_value=number(raw.get('System_Voltage_V', raw.get('Bus_Voltage_V'))),
                      price_usd=price, stock_qty=stock,
                      verification_status='unverified', engineering_eligible=False,
                      issues=issues, raw_fields=raw)
        # Only carry fields whose meaning is clear in their source schema.
        if kind == 'panel':
            record['vmp_v'] = number(raw.get('V_mp_or_MPPT_Min', raw.get('Vmp_or_MinMPPT_V', raw.get('Max_MPPT_V'))))
            record['voc_v'] = number(raw.get('V_oc_or_MPPT_Max', raw.get('Voc_or_MaxDC_V', raw.get('Max_DC_V'))))
        if kind == 'battery':
            dod = number(raw.get('Efficiency_or_DoD'))
            record['declared_dod'] = dod if dod is not None and 0 < dod <= 1 else None
        records.append(record)
    return dict(source_id=source['source_id'], records=records, skipped_rows=skipped)


def audit_snapshots(snapshots):
    records = [row for snapshot in snapshots for row in snapshot['records']]
    grouped = {}
    for row in records:
        # Item_ID is never a global identifier; exact model groups are review hints only.
        key = (row['category'], str(row['brand']).strip().casefold(), re.sub(r'\s+', ' ', str(row['model']).strip().casefold()))
        grouped.setdefault(key, []).append(row)
    conflicts = []
    for key, group in grouped.items():
        if len({x['source_id'] for x in group}) < 2:
            continue
        differing = [field for field in ('capacity_value', 'capacity_unit', 'price_usd', 'stock_qty', 'legacy_voltage_value')
                     if len({x.get(field) for x in group}) > 1]
        if differing:
            conflicts.append(dict(model=group[0]['model'], differing_fields=differing,
                                  record_ids=[x['record_id'] for x in group]))
    return dict(total_records=len(records), sources=[dict(source_id=s['source_id'], count=len(s['records'])) for s in snapshots],
                engineering_eligible_records=sum(x['engineering_eligible'] for x in records),
                exact_model_conflicts=conflicts,
                notes=['No cross-source stock addition or automatic deduplication.',
                       'Non-exact model aliases are not resolved; conflict list is not exhaustive.'])


def positive_value(name, value):
    parsed = number(value)
    if parsed is None or parsed <= 0:
        raise ValueError(f'{name} must be finite and positive')
    return parsed


def money(value):
    return str(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def commercial_shortlist(records, source_id, kind, minimum_capacity, capacity_unit, declared_ac_phase=None):
    positive_value('minimum_capacity', minimum_capacity)
    matches = []
    for row in records:
        if row['source_id'] != source_id or row['category'] != kind or row['capacity_unit'] != capacity_unit:
            continue
        if declared_ac_phase is not None and row['declared_ac_phase'] != declared_ac_phase:
            continue
        cap, price, stock = (row.get(k) for k in ('capacity_value', 'price_usd', 'stock_qty'))
        if any(number(x) is None for x in (cap, price, stock)):
            continue
        if cap >= minimum_capacity and price > 0 and stock >= 1 and stock == int(stock):
            matches.append(row)
    return sorted(matches, key=lambda r: (r['price_usd'], r['capacity_value']))


def build_commercial_draft(records, source_id, required_pv_w, required_continuous_w,
                           ac_phase=1, night_energy_wh=0, discharge_path_eff=0.95,
                           fx_rates=None, fx_as_of=None):
    """Capacity/price-only draft; NEVER a component compatibility recommendation.

    A single source prevents summing snapshot stock. Inverter count is always one.
    Panel count is an energy lower bound; string design may change it and its cost.
    Battery count uses each record's own declared DoD, not a global mixed assumption.
    """
    required_pv_w = positive_value('required_pv_w', required_pv_w)
    required_continuous_w = positive_value('required_continuous_w', required_continuous_w)
    if ac_phase not in (1, 3):
        raise ValueError('ac_phase must be 1 or 3')
    night_energy_wh = number(night_energy_wh)
    if night_energy_wh is None or night_energy_wh < 0:
        raise ValueError('night_energy_wh must be finite and nonnegative')
    discharge_path_eff = positive_value('discharge_path_eff', discharge_path_eff)
    if discharge_path_eff > 1:
        raise ValueError('discharge_path_eff must be <= 1')
    if not any(r['source_id'] == source_id for r in records):
        raise ValueError('unknown inventory source')
    lines, blocked = [], []

    def line(row, qty, assumption):
        return dict(record_id=row['record_id'], model=row['model'], category=row['category'],
                    quantity=qty, unit_price_usd=money(row['price_usd']),
                    subtotal_usd=money(Decimal(str(row['price_usd'])) * qty),
                    assumption=assumption, verification_status='unverified',
                    issues=row['issues'])

    panels = []
    for row in commercial_shortlist(records, source_id, 'panel', 1, 'W'):
        qty = math.ceil(required_pv_w / row['capacity_value'])
        if qty <= row['stock_qty']:
            panels.append((Decimal(str(row['price_usd'])) * qty, row, qty))
    if panels:
        _, selected, qty = min(panels, key=lambda x: (x[0], x[2]))
        lines.append(line(selected, qty, 'Energy-only lower-bound quantity; string engineering pending.'))
    else:
        blocked.append('No panel capacity/stock option in selected snapshot.')
    inverters = commercial_shortlist(records, source_id, 'inverter', required_continuous_w, 'W', ac_phase)
    if inverters:
        lines.append(line(inverters[0], 1, 'Capacity and declared phase only; AC/DC/PV and surge compatibility pending.'))
    else:
        blocked.append('No single inverter with sufficient declared continuous capacity and stock.')
    if night_energy_wh:
        batteries = []
        inv_bus = inverters[0].get('legacy_voltage_value') if inverters else None
        for row in commercial_shortlist(records, source_id, 'battery', 1, 'Wh'):
            # Nominal equality removes known conflicts only; it does not prove compatibility.
            # High-voltage ranges cannot be reconstructed from the legacy single value.
            if inv_bus is None or inv_bus > 60 or row.get('legacy_voltage_value') != inv_bus:
                continue
            dod = row.get('declared_dod')
            if dod is None:
                continue
            qty = math.ceil(night_energy_wh / (row['capacity_value'] * dod * discharge_path_eff))
            if qty <= row['stock_qty']:
                batteries.append((Decimal(str(row['price_usd'])) * qty, row, qty))
        if batteries:
            _, selected, qty = min(batteries, key=lambda x: (x[0], x[2]))
            lines.append(line(selected, qty, 'Energy arithmetic only; series/parallel, power and BMS compatibility unverified.'))
        else:
            blocked.append('No battery option within the same declared LV bus, energy and stock limits; HV range requires verification.')
    total = sum((Decimal(x['subtotal_usd']) for x in lines), Decimal(0))
    converted = {}
    if fx_rates:
        if not fx_as_of:
            raise ValueError('fx_as_of required for user-entered exchange rates')
        for label, rate in fx_rates.items():
            positive_value('exchange_rate', rate)
            converted[label] = money(total * Decimal(str(rate)))
    return dict(status='commercial_draft_not_engineering_design', is_final=False,
                source_id=source_id, lines=lines, blocked_items=blocked,
                listed_items_subtotal_usd=money(total), converted_subtotals=converted,
                exchange_rate_units='target currency units per 1 USD', exchange_rates=fx_rates or {}, fx_as_of=fx_as_of,
                missing_scope=['String-based final panel count', 'Cable sizing and quantities',
                               'Protection, earthing, mounting, labor, transport and taxes',
                               'Verified electrical and battery compatibility'],
                note='This may combine electrically incompatible items. Do not issue as a final customer quotation.')
