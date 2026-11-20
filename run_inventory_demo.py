"""Rebuild normalized inventory and write a clearly labelled commercial draft."""
import json
from pathlib import Path
from solar.inventory import import_snapshot, audit_snapshots, build_commercial_draft
from solar.engine import extract_appliances, size_loads


def run(output_dir=None):
    root = Path(__file__).parent
    out = Path(output_dir) if output_dir else root / 'outputs'
    out.mkdir(parents=True, exist_ok=True)
    snapshots = [import_snapshot(p) for p in sorted((root / 'data').glob('legacy_inventory_*.json'))]
    records = [r for s in snapshots for r in s['records']]
    audit = audit_snapshots(snapshots)
    config = json.loads((root / 'data/config.json').read_text(encoding='utf-8'))
    parsed = extract_appliances('ثلاجتين و ٣ شاشات و ١٠ لمبات و مكيفين', config['appliances'])
    sizing = size_loads(parsed['items'], psh=6.2)
    # Explicitly chosen 26-item snapshot; never merge stock across snapshots.
    source_id = '1i31mVTp9v0BaVhZSX5EKKgEdReeDKN3VnmQIEoGF4ck'
    draft = build_commercial_draft(records, source_id, sizing['required_pv_w'],
                                   sizing['minimum_continuous_inverter_w'], ac_phase=1)
    outputs = {'inventory_normalized.json': {'schema_version': '3.1-staging', 'records': records},
               'inventory_audit.json': audit,
               'commercial_draft_example.json': {'input_status': 'demonstration_defaults_only',
                                                   'message': 'ثلاجتين و ٣ شاشات و ١٠ لمبات و مكيفين',
                                                   'sizing': sizing, 'draft': draft}}
    for name, data in outputs.items():
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print('سجلات مستوردة:', audit['total_records'])
    print('سجلات مؤهلة هندسيًا:', audit['engineering_eligible_records'])
    print('مجموعات موديلات متطابقة ذات بيانات مختلفة:', len(audit['exact_model_conflicts']))
    print('مسودة تجارية تجريبية فقط — لم تُعتمد مطابقة المكونات:')
    for line in draft['lines']:
        print(f"{line['model']} | quantity={line['quantity']} | USD {line['subtotal_usd']}")
    print('مجموع البنود المعروضة فقط USD:', draft['listed_items_subtotal_usd'])
    print('لا يشمل عدد الألواح النهائي بعد تصميم السلاسل أو الحمايات والتركيب والبطاريات.')
    print('حُفظت النتائج في:', out)
    return audit, draft


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default=None)
    run(parser.parse_args().output_dir)
