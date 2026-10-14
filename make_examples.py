"""Generate reproducible datasets with documented ground truth."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from causal_studio.engine import sample_data

target = Path(__file__).parent / 'examples'
target.mkdir(exist_ok=True)
for mode in ('observational', 'timeseries'):
    sample_data(mode).to_csv(target/f'{mode}.csv', index=False, encoding='utf-8-sig')
rng = np.random.default_rng(25)
x, ey, ez = rng.exponential(size=(3, 4000)) - 1
y = .9*x + ey
z = .85*y + ez
pd.DataFrame({'X': x, 'Y': y, 'Z': z}).to_csv(target/'observational_nongaussian.csv', index=False, encoding='utf-8-sig')
(target/'ground_truth.json').write_text(json.dumps({
    'observational': {'seed': 2026, 'edges': [['环境条件','中间响应'],['设备输入','中间响应'],['中间响应','输出响应']], 'isolated': ['独立噪声'], 'noise': 'independent Gaussian'},
    'observational_nongaussian': {'seed':25, 'equations': ['X = Exp(1) - 1', 'Y = 0.9 X + (Exp(1) - 1)', 'Z = 0.85 Y + (Exp(1) - 1)'], 'noise': 'independent exponential, centered'},
    'timeseries': {'seed': 2026, 'burn_in': 200, 'edges': [['输入信号','输入信号',1,.65], ['输入信号','中间响应',1,.7], ['中间响应','中间响应',1,.35], ['中间响应','输出响应',2,-.65]]}
}, ensure_ascii=False, indent=2), encoding='utf-8')

# Additional examples used by the nonlinear and macOS packages.
rng = np.random.default_rng(42)
x = rng.uniform(-2, 2, 500)
pd.DataFrame({'X': x, 'Y': x*x + rng.normal(0, .2, len(x))}).to_csv(target/'observational_nonlinear.csv', index=False, encoding='utf-8-sig')
values = np.zeros((1400, 2))
noise = rng.exponential(size=values.shape) - 1
for t in range(1, len(values)):
    values[t, 0] = .55*values[t-1, 0] + noise[t, 0]
    values[t, 1] = .8*values[t, 0] + .65*values[t-1, 0] + noise[t, 1]
frame = pd.DataFrame(values[200:], columns=['X', 'Y'])
frame.insert(0, '时间', np.arange(len(frame)))
frame.to_csv(target/'timeseries_nongaussian.csv', index=False, encoding='utf-8-sig')
sample_data('observational').head(200).to_stata(target/'observational_demo.dta', write_index=False, version=118)
