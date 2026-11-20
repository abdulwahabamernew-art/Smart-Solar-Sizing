"""Revision-bound PV input screening with explicit unknowns and assumptions.

This does not approve complete systems or verify physical equipment identity.
"""
import math


def positive(name, value, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f'{name}: invalid numeric input')
    return value


def screen_array(panel, inverter, series, strings_by_mppt, required_pv_w,
                 min_cell_c, max_cell_c, bifacial_current_gain=0,
                 irradiance_current_factor=1.25, assumed_beta_vmp_per_c=None,
                 site_altitude_m=None, site_max_ambient_c=None,
                 physical_models_confirmed=False):
    """Single equal-length module string type, explicit MPPT distribution.

    Current gain is a scenario multiplier, not inferred annual energy yield.
    Current temperature correction uses alpha_isc as a conservative screening
    proxy for Imp too; this approximation is explicitly marked as assumed.
    """
    positive('required_pv_w', required_pv_w)
    if type(series) is not int or series <= 0:
        raise ValueError('series must be positive integer')
    if len(strings_by_mppt) != inverter['mppt_count'] or any(type(n) is not int or n < 0 for n in strings_by_mppt) or not sum(strings_by_mppt):
        raise ValueError('explicit nonnegative integer string count per MPPT required')
    if not all(isinstance(t, (int, float)) and math.isfinite(t) for t in (min_cell_c, max_cell_c)) or min_cell_c > max_cell_c:
        raise ValueError('invalid temperature interval')
    positive('bifacial_current_gain', bifacial_current_gain, zero=True)
    positive('irradiance_current_factor', irradiance_current_factor)
    if irradiance_current_factor < 1:
        raise ValueError('irradiance_current_factor must be >= 1')
    if assumed_beta_vmp_per_c is not None and not math.isfinite(assumed_beta_vmp_per_c):
        raise ValueError('invalid assumed beta Vmp')
    checks = []

    def check(name, state, detail):
        checks.append(dict(check=name, state=state, detail=detail))

    total_strings = sum(strings_by_mppt)
    panels = series * total_strings
    power = panels * panel['power_w']
    check('energy_capacity', 'pass' if power >= required_pv_w else 'fail', dict(array_stc_w=power, required_w=required_pv_w))
    check('pv_input_power', 'pass' if power <= inverter['max_pv_input_power_w'] else 'fail', dict(array_stc_w=power, limit_w=inverter['max_pv_input_power_w']))
    vocs = [panel['voc_v'] * (1 + panel['beta_voc_per_c'] * (t - 25)) for t in (min_cell_c, max_cell_c)]
    if min(vocs) <= 0:
        raise ValueError('invalid thermally corrected Voc')
    cold_voc = series * max(vocs)
    check('max_dc_voltage', 'pass' if cold_voc < inverter['max_dc_v'] else 'fail', dict(string_voc_max_v=cold_voc, exclusive_limit_v=inverter['max_dc_v']))
    if inverter.get('max_pv_access_power_w') is not None:
        check('pv_access_power', 'pass' if power <= inverter['max_pv_access_power_w'] else 'fail', dict(limit_w=inverter['max_pv_access_power_w']))
    beta = panel.get('beta_vmp_per_c')
    using_assumption = beta is None and assumed_beta_vmp_per_c is not None
    if beta is None:
        beta = assumed_beta_vmp_per_c
    vmp_range = None
    if beta is None:
        check('thermal_mppt', 'pending', 'Manufacturer beta Vmp not present in cited datasheet; no substitution from beta Voc or gamma Pmax.')
        check('startup_screen', 'pending', 'Temperature-corrected operating voltage unavailable; actual low-light startup also unmodeled.')
    else:
        vmps = [series * panel['vmp_v'] * (1 + beta * (t - 25)) for t in (min_cell_c, max_cell_c)]
        if min(vmps) <= 0:
            raise ValueError('invalid thermally corrected Vmp')
        vmp_range = [min(vmps), max(vmps)]
        ok = min(vmps) >= inverter['mppt_min_v'] and max(vmps) <= inverter['mppt_max_v']
        check('thermal_mppt', ('assumed_pass' if using_assumption else 'pass') if ok else 'fail', dict(string_vmp_min_v=min(vmps), string_vmp_max_v=max(vmps), beta_vmp=beta, manufacturer_coefficient=not using_assumption))
        check('startup_screen', ('assumed_pass' if using_assumption else 'pass') if min(vmps) >= inverter['startup_v'] else 'fail', dict(required_v=inverter['startup_v'], note='Voltage screening only, not low-irradiance startup simulation.'))
    temp_factor = max(1 + panel['alpha_isc_per_c'] * (t - 25) for t in (min_cell_c, max_cell_c))
    positive('current temperature factor', temp_factor)
    current_factor = (1 + bifacial_current_gain) * temp_factor
    imp_screen = panel['imp_a'] * current_factor
    isc_screen = panel['isc_a'] * current_factor * irradiance_current_factor
    check('current_model', 'assumed_pass', dict(imp_model='Imp scaled with alpha Isc proxy', irradiance_factor_applied_to='Isc', irradiance_factor=irradiance_current_factor, bifacial_current_gain=bifacial_current_gain, note='Scenario assumption; not a universal code factor or validated site maximum.'))
    for i, count in enumerate(strings_by_mppt):
        if not count:
            continue
        check(f'mppt_{i+1}_string_count', 'pass' if count <= inverter['max_strings_per_mppt'][i] else 'fail', dict(strings=count, limit=inverter['max_strings_per_mppt'][i]))
        check(f'mppt_{i+1}_operating_current', 'pass' if count * imp_screen <= inverter['max_operating_a_per_mppt'][i] else 'fail', dict(screen_a=count * imp_screen, limit_a=inverter['max_operating_a_per_mppt'][i]))
        per_string = inverter.get('max_operating_a_per_string')
        if per_string is not None:
            check(f'mppt_{i+1}_per_string_current', 'pass' if imp_screen <= per_string else 'fail', dict(screen_a=imp_screen, limit_a=per_string))
        isc_limits = inverter.get('max_isc_a_per_mppt')
        if isc_limits is None:
            check(f'mppt_{i+1}_short_circuit_current', 'pending', 'Independent PV short-circuit limit not established in selected document.')
        else:
            check(f'mppt_{i+1}_short_circuit_current', 'pass' if count * isc_screen <= isc_limits[i] else 'fail', dict(screen_a=count * isc_screen, limit_a=isc_limits[i]))
    if not physical_models_confirmed:
        check('physical_revision_match', 'pending', 'Legacy inventory names do not prove exact model suffix, hardware revision or matching datasheet.')
    if site_altitude_m is None or inverter.get('max_altitude_m') is None:
        check('site_altitude', 'pending', 'Site altitude not supplied.')
    else:
        positive('site_altitude_m', site_altitude_m, zero=True)
        check('site_altitude', 'pass' if site_altitude_m <= inverter['max_altitude_m'] else 'fail', dict(site_m=site_altitude_m, limit_m=inverter['max_altitude_m']))
    if site_max_ambient_c is None:
        check('ambient_derating', 'pending', 'Ambient temperature and installation conditions not supplied.')
    else:
        if not isinstance(site_max_ambient_c, (int, float)) or not math.isfinite(site_max_ambient_c):
            raise ValueError('invalid ambient temperature')
        if site_max_ambient_c > inverter['max_ambient_c']:
            check('ambient_derating', 'fail', 'Ambient exceeds documented maximum.')
        elif site_max_ambient_c > inverter.get('derating_starts_c', inverter['max_ambient_c']):
            check('ambient_derating', 'pending', 'Requires manufacturer derating curve; do not use full nameplate power.')
        else:
            check('ambient_derating', 'pass', 'Below documented upper-temperature/derating threshold; ventilation and minimum temperature not evaluated.')
    failures = [c for c in checks if c['state'] == 'fail']
    provisional = any(c['state'] in ('pending', 'assumed_pass') for c in checks)
    return dict(status='rejected' if failures else ('conditional' if provisional else 'pv_screen_pass'),
                installation_approved=False, panel_profile=panel['profile_id'], inverter_profile=inverter['profile_id'],
                series=series, strings_by_mppt=strings_by_mppt, panels=panels, array_stc_w=power,
                checks=checks, failed_checks=[c['check'] for c in failures],
                string_vmp_range_v=vmp_range,
                excluded_scope=['Battery/BMS', 'AC load and surge validation', 'Cable/protection/earthing', 'Site irradiance extremes', 'Minimum ambient temperature and ventilation', 'Structural design'])


def enumerate_arrays(panel, inverter, required_pv_w, **conditions):
    """Enumerate equal-length strings. Keep assumptions distinct from verified limits."""
    from itertools import product
    positive('required_pv_w', required_pv_w)
    voc_max = max(panel['voc_v'] * (1 + panel['beta_voc_per_c'] * (t - 25)) for t in (conditions['min_cell_c'], conditions['max_cell_c']))
    positive('corrected Voc', voc_max)
    max_series = math.floor(inverter['max_dc_v'] / voc_max)
    candidates = []
    rejected = 0
    for series in range(1, max_series + 1):
        for distribution in product(*(range(n + 1) for n in inverter['max_strings_per_mppt'])):
            if not sum(distribution) or series * sum(distribution) * panel['power_w'] < required_pv_w:
                continue
            result = screen_array(panel, inverter, series, list(distribution), required_pv_w, **conditions)
            if result['status'] == 'rejected':
                rejected += 1
            else:
                candidates.append(result)
    candidates.sort(key=lambda r: (r['panels'], max(r['strings_by_mppt']), sum(r['strings_by_mppt']), -r['series']))
    return dict(status='conditional_candidates' if candidates else 'no_candidates_under_selected_limits',
                candidates=candidates, rejected_candidate_count=rejected,
                installation_approved=False)
