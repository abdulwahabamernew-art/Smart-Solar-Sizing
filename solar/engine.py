"""Explicit SI units; estimates, not installation approval."""
import math
import re
from dataclasses import dataclass
from typing import Optional


def positive(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and > 0')
    return value


def fraction(name, value):
    positive(name, value)
    if value > 1:
        raise ValueError(f'{name} must be <= 1')
    return value


def hours_valid(value):
    positive('hours', value)
    if value > 24:
        raise ValueError('hours must be <= 24')
    return value


def normalize(text):
    text = str(text).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹أإآىة', '01234567890123456789ااايه'))
    return re.sub(r'[\u064b-\u065f\u0670ـ]', '', text).lower()


def extract_appliances(text, catalog):
    """Conservative parser: quantity before name; watt/hour overrides require units.

    Returns unresolved chunks and assumptions for user confirmation. No silent
    interpretation of an unlabelled number after an appliance as its quantity.
    """
    normalized = normalize(text)
    aliases = {}
    for name, spec in catalog.items():
        for alias in [name] + spec.get('aliases', []):
            key = normalize(alias)
            if key in aliases and aliases[key] != name:
                raise ValueError(f'ambiguous alias: {alias}')
            aliases[key] = name
    alternatives = '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    pattern = re.compile(r'(?<!\w)(?:(\d+)\s+)?(' + alternatives + r')(?!\w)')
    matches = list(pattern.finditer(normalized))
    items, warnings, unresolved = [], [], []
    prefix = normalized[:matches[0].start()] if matches else normalized
    if prefix.strip():
        unresolved.append(prefix.strip())
    for i, match in enumerate(matches):
        name = aliases[match[2]]
        spec = catalog[name]
        tail = normalized[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(normalized)]
        dual = match[2].endswith(('تين', 'ين'))
        qty = int(match[1]) if match[1] else (2 if dual else 1)
        positive('quantity', qty)
        watts_match = re.search(r'(\d+(?:\.\d+)?)\s*(كيلوواط|كيلووات|واط|وات|kw|w)(?!\w)', tail)
        time_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:ساعات|ساعه|ساعة|hours?|h)(?!\w)', tail)
        watts = float(watts_match[1]) if watts_match else spec['default_watts']
        if watts_match and watts_match[2] in ('كيلوواط', 'كيلووات', 'kw'):
            watts *= 1000
        hours = float(time_match[1]) if time_match else spec['default_hours']
        positive('watts', watts)
        hours_valid(hours)
        assumptions = []
        if not match[1] and not dual:
            assumptions.append('quantity_default_1')
        if not watts_match:
            assumptions.append('default_watts')
        if not time_match:
            assumptions.append('default_hours')
        items.append(dict(appliance=name, quantity=qty, watts=watts, hours=hours,
                          surge_factor=spec.get('surge_factor', 1), assumptions=assumptions))
        rest = tail
        for token in (watts_match, time_match):
            if token:
                rest = rest.replace(token[0], ' ')
        rest = re.sub(r'(?:لمده|عدد|يوميا|باليوم)', ' ', rest)
        rest = re.sub(r'[\s،,؛;+.و]+', ' ', rest).strip()
        if rest:
            unresolved.append(rest)
    if unresolved:
        warnings.append('Unresolved text requires review; calculation must use confirmed items.')
    return dict(items=items, unresolved=unresolved, warnings=warnings, requires_confirmation=True)


def size_loads(items, psh, performance_ratio=0.75, night_energy_wh=None,
               autonomy_days=1, battery_dod=0.8, discharge_path_eff=0.95):
    positive('PSH', psh)
    fraction('performance_ratio', performance_ratio)
    if not items:
        raise ValueError('confirmed loads required')
    energy, running, largest_increment = 0, 0, 0
    for item in items:
        q = positive('quantity', item['quantity'])
        if q != int(q):
            raise ValueError('quantity must be an integer')
        w = positive('watts', item['watts'])
        h = hours_valid(item['hours'])
        surge = positive('surge_factor', item.get('surge_factor', 1))
        if surge < 1:
            raise ValueError('surge_factor must be >= 1')
        energy += q * w * h
        running += q * w
        # Assumes one motor starts at a time; all other loads already running.
        largest_increment = max(largest_increment, w * (surge - 1))
    result = dict(daily_energy_wh=energy, running_w=running,
                  preliminary_starting_va=running + largest_increment,
                  minimum_continuous_inverter_w=running * 1.25,
                  required_pv_w=energy / (psh * performance_ratio),
                  battery_nominal_wh=None,
                  assumptions=['All loads concurrent; unity PF for preliminary starting estimate.',
                               'One motor starts at a time; validate actual VA and surge duration.',
                               'PV calculation is a daily energy balance, not hourly dispatch.'])
    if night_energy_wh is not None:
        if not math.isfinite(night_energy_wh) or not 0 <= night_energy_wh <= energy:
            raise ValueError('night_energy_wh must be between zero and daily energy')
        positive('autonomy_days', autonomy_days)
        fraction('battery_dod', battery_dod)
        fraction('discharge_path_eff', discharge_path_eff)
        result['battery_nominal_wh'] = night_energy_wh * autonomy_days / (battery_dod * discharge_path_eff)
    return result


def size_well(tdh_m, volume_m3_day, psh, pumping_hours, pump_eff=0.60,
              motor_eff=0.85, vfd_eff=0.96, pv_derating=0.80):
    for k, v in dict(tdh_m=tdh_m, volume_m3_day=volume_m3_day, psh=psh).items():
        positive(k, v)
    hours_valid(pumping_hours)
    for k, v in dict(pump_eff=pump_eff, motor_eff=motor_eff, vfd_eff=vfd_eff, pv_derating=pv_derating).items():
        fraction(k, v)
    hydraulic = 1000 * 9.81 * volume_m3_day * tdh_m / 3.6e6
    shaft_kw = hydraulic / (pumping_hours * pump_eff)
    return dict(hydraulic_energy_kwh_day=hydraulic,
                electrical_energy_kwh_day=hydraulic / (pump_eff * motor_eff * vfd_eff),
                estimated_shaft_kw=shaft_kw, estimated_shaft_hp=shaft_kw / 0.746,
                motor_electrical_kw=shaft_kw / motor_eff,
                required_pv_w=1000 * hydraulic / (pump_eff * motor_eff * vfd_eff * psh * pv_derating),
                assumptions=['TDH must include dynamic lift, pressure and friction losses.',
                             'Constant flow and efficiencies; pump curve and hourly solar check required.',
                             'VFD selection needs rated motor current, voltage, frequency and overload data.'])


def size_existing_pump(shaft_hp, operating_hours, psh, motor_eff=0.85, vfd_eff=0.96, pv_derating=0.80):
    positive('shaft_hp', shaft_hp)
    hours_valid(operating_hours)
    positive('PSH', psh)
    for k, v in dict(motor_eff=motor_eff, vfd_eff=vfd_eff, pv_derating=pv_derating).items():
        fraction(k, v)
    input_kw = shaft_hp * 0.746 / (motor_eff * vfd_eff)
    return dict(electrical_energy_kwh_day=input_kw * operating_hours,
                required_pv_w=input_kw * operating_hours * 1000 / (psh * pv_derating),
                assumptions=['HP is shaft output rating; assumes full load throughout operating hours.',
                             'Does not establish daily water volume or instantaneous solar feasibility.'])


def size_motor_load(shaft_hp, other_running_kw, operating_hours, psh,
                    motor_eff=0.88, power_factor=0.85, starting_current_factor=None,
                    starting_duration_seconds=None, performance_ratio=0.78):
    """Industrial/commercial estimate. Starting factor must be supplied explicitly.

    Uses running PF only as a proxy for rated VA; starting PF differs, so output
    is a preliminary VA requirement, never a verified transient simulation.
    """
    positive('shaft_hp', shaft_hp)
    if not math.isfinite(other_running_kw) or other_running_kw < 0:
        raise ValueError('other_running_kw must be finite and >= 0')
    hours_valid(operating_hours)
    positive('PSH', psh)
    for k, v in dict(motor_eff=motor_eff, power_factor=power_factor, performance_ratio=performance_ratio).items():
        fraction(k, v)
    motor_kw = shaft_hp * 0.746 / motor_eff
    total_kw = motor_kw + other_running_kw
    result = dict(motor_running_kw=motor_kw, total_running_kw=total_kw,
                  daily_energy_kwh=total_kw * operating_hours,
                  required_pv_w=1000 * total_kw * operating_hours / (psh * performance_ratio),
                  minimum_continuous_inverter_w=total_kw * 1250,
                  preliminary_starting_va=None, starting_duration_seconds=None,
                  assumptions=['Other load assumed unity PF and concurrent.',
                               'Starting current factor is a user-supplied estimate; verify motor/drive datasheets.',
                               'No hourly dispatch or battery power sizing performed.'])
    if starting_current_factor is not None:
        positive('starting_current_factor', starting_current_factor)
        if starting_current_factor < 1:
            raise ValueError('starting_current_factor must be >= 1')
        positive('starting_duration_seconds', starting_duration_seconds)
        result['preliminary_starting_va'] = 1000 * (motor_kw / power_factor * starting_current_factor + other_running_kw)
        result['starting_duration_seconds'] = starting_duration_seconds
    return result


@dataclass(frozen=True)
class Panel:
    power_w: float
    voc_v: float
    vmp_v: float
    isc_a: float
    imp_a: float
    beta_voc_per_c: float
    beta_vmp_per_c: float


@dataclass(frozen=True)
class PVInput:
    max_dc_v: float
    mppt_min_v: float
    mppt_max_v: float
    max_operating_current_a_per_mppt: float
    max_short_circuit_current_a_per_mppt: float
    mppt_count: int
    max_strings_per_mppt: int
    max_pv_power_w: float


def design_array(required_pv_w, panel, inverter, min_cell_c, max_cell_c, isc_multiplier=1.25):
    """Enumerate equal-length strings; smallest compliant array, balanced MPPTs.

    isc_multiplier is an explicit design assumption, not a universal code rule.
    Starting voltage, bifacial current gain, connectors and protective devices
    must be checked separately against manufacturer data.
    """
    positive('required_pv_w', required_pv_w)
    positive('isc_multiplier', isc_multiplier)
    if isc_multiplier < 1:
        raise ValueError('isc_multiplier must be >= 1')
    for name in ('power_w', 'voc_v', 'vmp_v', 'isc_a', 'imp_a'):
        positive(name, getattr(panel, name))
    if panel.vmp_v >= panel.voc_v or panel.imp_a > panel.isc_a:
        raise ValueError('inconsistent panel ratings')
    for name, value in vars(inverter).items():
        positive(name, value)
    for name in ('mppt_count', 'max_strings_per_mppt'):
        if getattr(inverter, name) != int(getattr(inverter, name)):
            raise ValueError(f'{name} must be integer')
    if not (inverter.mppt_min_v <= inverter.mppt_max_v < inverter.max_dc_v):
        raise ValueError('invalid inverter voltage limits')
    if not all(math.isfinite(x) for x in (min_cell_c, max_cell_c, panel.beta_voc_per_c, panel.beta_vmp_per_c)) or min_cell_c > max_cell_c:
        raise ValueError('invalid temperatures or coefficients')
    voc_max = max(panel.voc_v * (1 + panel.beta_voc_per_c * (t - 25)) for t in (min_cell_c, max_cell_c))
    vmp_values = [panel.vmp_v * (1 + panel.beta_vmp_per_c * (t - 25)) for t in (min_cell_c, max_cell_c)]
    vmp_low, vmp_high = min(vmp_values), max(vmp_values)
    positive('corrected_vmp', vmp_low)
    positive('corrected_voc', voc_max)
    n_min = max(1, math.ceil(inverter.mppt_min_v / vmp_low))
    n_max = min(math.floor(inverter.max_dc_v / voc_max), math.floor(inverter.mppt_max_v / vmp_high))
    strings_per_mppt = min(int(inverter.max_strings_per_mppt),
                           math.floor(inverter.max_operating_current_a_per_mppt / panel.imp_a),
                           math.floor(inverter.max_short_circuit_current_a_per_mppt / (panel.isc_a * isc_multiplier)))
    solutions = []
    for series in range(n_min, n_max + 1):
        parallel = math.ceil(required_pv_w / (series * panel.power_w))
        if parallel > inverter.mppt_count * strings_per_mppt:
            continue
        power = series * parallel * panel.power_w
        if power > inverter.max_pv_power_w:
            continue
        distribution = [parallel // int(inverter.mppt_count) + (i < parallel % int(inverter.mppt_count)) for i in range(int(inverter.mppt_count))]
        solutions.append(dict(series=series, parallel_strings=parallel,
                              panels=series * parallel, actual_pv_w=power,
                              strings_by_mppt=distribution, string_voc_max_v=series * voc_max,
                              string_vmp_min_v=series * vmp_low, string_vmp_max_v=series * vmp_high))
    if not solutions:
        raise ValueError('No feasible array within voltage, current, string and PV power limits')
    return min(solutions, key=lambda s: (s['panels'], s['parallel_strings']))


def recommend_inverters(inventory, required_continuous_w, ac_phase, ac_voltage_v,
                        battery_voltage_v=None, required_surge_va=None, required_surge_seconds=None):
    """Hard compatibility filter, then ascending price/oversize. Missing ratings reject.

    AC phase/voltage and battery bus are separate. No implicit parallel units.
    PV-input compatibility must also be checked through design_array.
    """
    positive('required_continuous_w', required_continuous_w)
    if ac_phase not in (1, 3):
        raise ValueError('ac_phase must be 1 or 3')
    positive('ac_voltage_v', ac_voltage_v)
    if battery_voltage_v is not None:
        positive('battery_voltage_v', battery_voltage_v)
    if required_surge_va is not None:
        positive('required_surge_va', required_surge_va)
        positive('required_surge_seconds', required_surge_seconds)
    valid, rejected = [], []
    for row in inventory:
        reasons = []
        if row.get('verification_status') != 'verified' or not row.get('datasheet_source'):
            reasons.append('manufacturer_ratings_unverified')
        needed = ['id', 'category', 'continuous_w', 'ac_phase', 'ac_voltage_v', 'price_usd', 'stock_qty']
        if any(row.get(k) is None for k in needed):
            rejected.append(dict(id=row.get('id'), reasons=['missing_required_data']))
            continue
        try:
            positive('continuous_w', row['continuous_w'])
            positive('price_usd', row['price_usd'])
            positive('stock_qty', row['stock_qty'])
        except ValueError:
            reasons.append('invalid_capacity_price_or_stock')
        if row['category'] != 'inverter' or row['ac_phase'] != ac_phase or row['ac_voltage_v'] != ac_voltage_v:
            reasons.append('category_or_ac_mismatch')
        if row['continuous_w'] < required_continuous_w:
            reasons.append('insufficient_continuous_capacity')
        if battery_voltage_v is not None:
            lo, hi = row.get('battery_min_v'), row.get('battery_max_v')
            if lo is None or hi is None or not lo <= battery_voltage_v <= hi:
                reasons.append('battery_range_unverified_or_incompatible')
        if required_surge_va is not None:
            if row.get('surge_va', 0) < required_surge_va or row.get('surge_seconds', 0) < required_surge_seconds:
                reasons.append('insufficient_or_missing_surge_rating')
        if reasons:
            rejected.append(dict(id=row['id'], reasons=reasons))
        else:
            valid.append(dict(row, oversize_ratio=row['continuous_w'] / required_continuous_w,
                              requires_pv_compatibility_check=True))
    return dict(candidates=sorted(valid, key=lambda r: (r['price_usd'], r['oversize_ratio'])), rejected=rejected)
