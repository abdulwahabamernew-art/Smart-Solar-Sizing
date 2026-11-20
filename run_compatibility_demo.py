import json
from pathlib import Path
from solar.compatibility import screen_array, enumerate_arrays


def run(output_dir=None):
    root = Path(__file__).parent
    profiles = json.loads((root / 'data/manufacturer_profiles.json').read_text(encoding='utf-8'))
    panel = profiles['panel']
    growatt, deye = profiles['inverters']
    # Synthetic site envelope for software tests, not documented climate of Sana'a.
    conditions = dict(min_cell_c=0, max_cell_c=70, site_altitude_m=1000,
                      site_max_ambient_c=40, bifacial_current_gain=0.10)
    required = 24660 / (6.2 * 0.75)
    cases = {
        'growatt_single_string': screen_array(panel, growatt, 7, [1], 4000, **conditions),
        'growatt_original_load': enumerate_arrays(panel, growatt, required, **conditions),
        'deye_5s_2mppt_evidence_only': screen_array(panel, deye, 5, [1, 1], required, **conditions),
        'deye_5s_2mppt_assumption_scenario': screen_array(panel, deye, 5, [1, 1], required, assumed_beta_vmp_per_c=-0.003, **conditions),
        'deye_5s_2strings_same_mppt': screen_array(panel, deye, 5, [2, 0], required, **conditions),
        'deye_altitude_2300m': screen_array(panel, deye, 5, [1, 1], required,
                                         **dict(conditions, site_altitude_m=2300)),
        'deye_candidates': enumerate_arrays(panel, deye, required, **conditions)
    }
    out = Path(output_dir) if output_dir else root / 'outputs'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'compatibility_cases.json').write_text(json.dumps({'conditions': conditions, 'required_pv_w': required, 'cases': cases}, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, case in cases.items():
        print(name, '=>', case['status'], '| failures:', ', '.join(case.get('failed_checks', [])))
    scenario = cases['deye_5s_2mppt_assumption_scenario']
    print('Deye scenario panels:', scenario['panels'], 'PV W:', scenario['array_stc_w'])
    print('Assumed thermal Vmp range V:', scenario['string_vmp_range_v'])
    print('الحالة conditional ليست اعتمادًا؛ معامل Vmp مفترض ومطابقة إصدار المعدات غير مثبتة.')
    print('حفظ النتائج:', out)
    return cases


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir')
    run(parser.parse_args().output_dir)
