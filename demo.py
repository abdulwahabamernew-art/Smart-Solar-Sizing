import json
from pathlib import Path
from solar.engine import extract_appliances, size_loads, size_well, design_array, Panel, PVInput

config = json.loads((Path(__file__).parent / 'data/config.json').read_text(encoding='utf-8'))
parsed = extract_appliances('ثلاجتين و ٣ شاشات و ١٠ لمبات و مكيفين', config['appliances'])
print(json.dumps(parsed, ensure_ascii=False, indent=2))
print('Demo only: treating the above defaults as confirmed:')
print(json.dumps(size_loads(parsed['items'], psh=6.2), indent=2))
well = size_well(tdh_m=150, volume_m3_day=180, psh=6.2, pumping_hours=7)
print(json.dumps(well, indent=2))
# Synthetic electrical ratings for algorithm demonstration; not a real product.
panel = Panel(710, 48.6, 40.65, 19, 17.5, -0.0025, -0.0029)
pv_input = PVInput(850, 480, 800, 40, 50, 2, 2, 50000)
print(json.dumps(design_array(well['required_pv_w'], panel, pv_input, 0, 58), indent=2))
