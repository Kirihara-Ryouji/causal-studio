from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
import zipfile
from collections import defaultdict
from html import escape
from pathlib import Path

KIND_LABELS = {"directed": "有向 →", "undirected": "未定向 —", "bidirected": "潜在混杂 ↔",
               "circle_circle": "未定向 ○—○", "circle_arrow": "部分定向 ○→",
               "tail_circle": "部分定向 —○", "conflict": "方向冲突 ×—×",
               "reverse_directed": "有向 ←", "arrow_circle": "部分定向 ←○", "circle_tail": "部分定向 ○—"}


def graph_geometry(result):
    names = result["columns"]
    n = len(names)
    width = max(1000, n * 70)
    height = max(680, n * 45)
    cx, cy = width / 2, height / 2 + 15
    rx, ry = width * .34, height * .33
    positions = {name: (cx + rx * math.cos(-math.pi/2 + k*2*math.pi/n),
                        cy + ry * math.sin(-math.pi/2 + k*2*math.pi/n)) for k, name in enumerate(names)}
    for name, point in result.get('graph_layout', {}).items():
        if name in positions and len(point) == 2 and all(math.isfinite(v) for v in point):
            positions[name] = tuple(point)
    left = min(0, min(x for x,y in positions.values()) - 130)
    top = min(0, min(y for x,y in positions.values()) - 190)
    right = max(width, max(x for x,y in positions.values()) + 130)
    bottom = max(height, max(y for x,y in positions.values()) + 100)
    return positions, (left, top, right-left, bottom-top)


def graph_svg(result: dict, include_nodes=True) -> str:
    names = result['columns']
    positions, (left, top, width, height) = graph_geometry(result)
    cx, cy = left+width/2, top+height/2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{left} {top} {width} {height}">',
             f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#f8fafc"/>',
             '<g font-family="Microsoft YaHei,PingFang SC,Arial,sans-serif">',
             f'<text x="{left+30}" y="{top+38}" fill="#173343" font-size="20" font-weight="bold">{escape(result["algorithm"])}</text>',
             f'<text x="{left+30}" y="{top+64}" fill="#627687" font-size="13">候选因果结构 · 方向与端点须结合算法假设解读</text>']
    groups = defaultdict(list)
    for edge in result["edges"]:
        groups[(edge["source"], edge["target"], edge["kind"])].append(edge["lag"])

    def endpoint(x, y, dx, dy, kind, color):
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        if kind == "arrow":
            pts = [(x, y), (x-12*ux+5*uy, y-12*uy-5*ux), (x-12*ux-5*uy, y-12*uy+5*ux)]
            return '<polygon points="' + ' '.join(f'{a:.1f},{b:.1f}' for a,b in pts) + f'" fill="{color}"/>'
        if kind == "circle":
            return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#f8fafc" stroke="{color}" stroke-width="2"/>'
        if kind == "cross":
            return f'<path d="M {x-5} {y-5} L {x+5} {y+5} M {x+5} {y-5} L {x-5} {y+5}" stroke="{color}" stroke-width="2"/>'
        return ""

    for (source, target, kind), lags in groups.items():
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        color = "#d29443" if kind == "conflict" else "#258d89" if kind == "directed" else "#7c8aab"
        if source == target:
            ax, ay, bx, by = x1-30, y1-29, x1+30, y1-29
            c1x, c1y, c2x, c2y = x1-85, y1-120, x1+85, y1-120
            path = f'M {ax} {ay} C {c1x} {c1y} {c2x} {c2y} {bx} {by}'
            tx, ty = x1, y1-101
        else:
            dx, dy = x2-x1, y2-y1
            if math.hypot(dx, dy) < 1e-6:
                dx = 1e-6
            length = math.hypot(dx, dy)
            ux, uy = dx/length, dy/length
            boundary = 1 / math.sqrt((ux/91)**2 + (uy/31)**2)
            ax, ay, bx, by = x1+ux*boundary, y1+uy*boundary, x2-ux*boundary, y2-uy*boundary
            bend = 28 if any(k[0] == target and k[1] == source for k in groups) else 0
            mx, my = (ax+bx)/2 - uy*bend, (ay+by)/2 + ux*bend
            c1x, c1y, c2x, c2y = mx, my, mx, my
            path = f'M {ax} {ay} Q {mx} {my} {bx} {by}'
            tx, ty = (ax+2*mx+bx)/4, (ay+2*my+by)/4-9
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        start, end = {"directed": ("tail", "arrow"), "undirected": ("tail", "tail"),
                      "bidirected": ("arrow", "arrow"), "circle_circle": ("circle", "circle"),
                      "circle_arrow": ("circle", "arrow"), "tail_circle": ("tail", "circle"),
                      "conflict": ("cross", "cross"), "reverse_directed": ("arrow", "tail"),
                      "arrow_circle": ("arrow", "circle"), "circle_tail": ("circle", "tail")}[kind]
        parts.extend([endpoint(ax, ay, ax-c1x, ay-c1y, start, color),
                      endpoint(bx, by, bx-c2x, by-c2y, end, color)])
        if result["settings"]["mode"] == "timeseries":
            label = "τ=" + ",".join(map(str, sorted(lags)))
            parts.append(f'<text x="{tx}" y="{ty}" text-anchor="middle" fill="{color}" font-size="13">{label}</text>')
    for name in (names if include_nodes else []):
        x, y = positions[name]
        parts.append(f'<ellipse cx="{x}" cy="{y}" rx="91" ry="31" fill="white" stroke="#cddde4" stroke-width="2"/>')
        label = name if len(name) <= 12 else name[:11] + "…"
        parts.append(f'<text x="{x}" y="{y+5}" text-anchor="middle" font-size="14" fill="#173343"><title>{escape(name)}</title>{escape(label)}</text>')
    if not result["edges"]:
        parts.append(f'<text x="{cx}" y="{cy}" text-anchor="middle" font-size="17" fill="#627687">当前设置下未发现关系</text>')
    parts.append(f'<text x="{left+30}" y="{top+height-25}" fill="#627687" font-size="12">箭头：有向 · 直线：未定向 · 圆：不确定端点 · 双箭头：潜在混杂（FCI / LPCMCI） · 叉：方向冲突</text></g></svg>')
    return "".join(parts)


def value_text(value):
    return "—" if value is None else f"{value:.5g}"


def statistic_label(result):
    cfg = result['settings']
    if cfg['algorithm'] in ('lingam', 'varlingam'):
        return '标准化结构系数'
    label = {'parcorr': '偏相关统计量', 'gpdc': '残差距离相关统计量',
             'cmiknn': '条件互信息统计量'}.get(cfg.get('temporal_test', 'parcorr'), '检验统计量')
    return ('搜索记录的' if cfg['algorithm'] == 'lpcmci' else '') + label


def structure_text(result: dict) -> str:
    """Readable, explicit endpoint semantics; retain full variable names."""
    quote = lambda name: json.dumps(str(name), ensure_ascii=False)
    marks = {'directed':'-->', 'undirected':'---', 'bidirected':'<->',
             'circle_circle':'o-o', 'circle_arrow':'o->', 'tail_circle':'--o', 'conflict':'x-x',
             'reverse_directed':'<--', 'arrow_circle':'<-o', 'circle_tail':'o--'}
    temporal = result['settings']['mode'] == 'timeseries'
    lines = ['因果结构文本', '='*36, f"算法：{result['algorithm']}",
             f"生成时间：{result['created_at']}", f"数据来源：{quote(result['source'].get('name', '未指定'))}",
             f"有效样本：{result['rows_used']}；变量：{len(result['columns'])}；候选关系：{len(result['edges'])}",
             '', '一、变量（完整名称）']
    lines += [f'{i}. {quote(name)}' for i,name in enumerate(result['columns'],1)]
    lines += ['', '二、候选因果结构']
    for i, edge in enumerate(result['edges'],1):
        source, target = quote(edge['source']), quote(edge['target'])
        if temporal:
            source += f"(t-{edge['lag']})" if edge['lag'] else '(t)'
            target += '(t)'
        details = [KIND_LABELS[edge['kind']]]
        if edge['statistic'] is not None:
            label = statistic_label(result)
            details.append(label + '=' + value_text(edge['statistic']))
        for key, label in [('p_value','p'),('q_value','q')]:
            if edge[key] is not None:
                details.append(label + '=' + value_text(edge[key]))
        lines.append(f"{i}. {source} {marks[edge['kind']]} {target}  [" + '；'.join(details) + ']')
    if not result['edges']:
        lines.append('当前设置下未发现关系；这不证明变量之间不存在因果联系。')
    connected = {e[k] for e in result['edges'] for k in ('source','target')}
    isolated = [quote(n) for n in result['columns'] if n not in connected]
    if isolated:
        lines += ['', '未连接变量：' + '、'.join(isolated)]
    lines += ['', '三、符号说明', '--> 有向；--- 未定向；o 表示不确定端点；x-x 表示方向冲突。',
              '<-> 在 FCI / LPCMCI 中表示潜在混杂结构，不表示双向因果。',
              '时间序列中的 t-k 表示提前 k 个采样步长；t 表示同期。',
              '图中拖动位置只改变布局，不改变本结构文本中的关系。', '', '四、适用条件与解释']
    lines += ['• ' + s for s in result['assumptions']]
    lines += ['', '五、数据处理记录'] + (result['notes'] or ['无额外处理提示。'])
    lines += ['', '六、分析参数', json.dumps(result['settings'], ensure_ascii=False, indent=2)]
    return '\n'.join(lines) + '\n'


def report_html(result: dict) -> str:
    def li(items):
        return "".join("<li>" + escape(item) + "</li>" for item in items)
    rows = "".join("<tr>" + "".join("<td>" + escape(str(v)) + "</td>" for v in (
        e["source"], KIND_LABELS[e["kind"]], e["target"], e["lag"], value_text(e["statistic"]),
        value_text(e["p_value"]), value_text(e["q_value"]))) + "</tr>" for e in result["edges"])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>因果发现报告</title>
<style>body{{font:15px/1.8 'Microsoft YaHei','PingFang SC',sans-serif;max-width:1120px;margin:40px auto;color:#173343;background:#f8fafc;padding:24px}}h1{{font-size:30px}}h2{{margin-top:32px}}table{{width:100%;border-collapse:collapse;background:white}}td,th{{text-align:left;padding:9px;border-bottom:1px solid #dce6eb}}svg{{width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.note{{padding:16px;background:#e5f3f1;border-radius:10px}}</style>
<h1>因果发现分析报告</h1><p>{escape(result['algorithm'])} · {escape(result['created_at'])}</p>
<div class="note">原始样本 {result['rows_original']:,} · 有效样本 {result['rows_used']:,} · 变量 {len(result['columns'])} · 候选关系 {len(result['edges'])}<br>结果依赖算法假设，不能单凭此图确认因果。不同算法的边数和统计量不用于直接评定优劣。</div>
{graph_svg(result)}<h2>关系明细</h2><table><tr><th>源变量</th><th>类型</th><th>目标变量</th><th>滞后</th><th>统计量 / 系数</th><th>p 值</th><th>q 值</th></tr>{rows}</table>
<p>PC / FCI / GES 不提供可直接解释为“边显著性”的单一 p 值。DirectLiNGAM / VARLiNGAM 显示标准化系数；RESIT 不提供效应系数。时序方法的统计量随检验选项变化，LPCMCI 显示搜索记录值。</p>
<h2>成立条件与解释</h2><ul>{li(result['assumptions'])}</ul><h2>数据处理记录</h2><ul>{li(result['notes'] or ['所选变量未触发额外数据处理提示。'])}</ul>
<h2>可复核配置</h2><pre>{escape(json.dumps({k:result[k] for k in ('source','settings','versions','category_encodings')},ensure_ascii=False,indent=2))}</pre></html>'''


def _safe_csv(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_bundle(path: str, result: dict):
    """Single atomic artifact; never include raw data."""
    destination = Path(path)
    stream = io.StringIO(newline="")
    fields = ["source", "target", "kind", "lag", "statistic", "p_value", "q_value"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows({k: _safe_csv(edge[k]) for k in fields} for edge in result["edges"])
    fd, temp = tempfile.mkstemp(prefix=".causal-export-", suffix=".zip", dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("result.json", json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            archive.writestr("edges.csv", "\ufeff" + stream.getvalue())
            archive.writestr("graph.svg", graph_svg(result))
            archive.writestr("structure.txt", structure_text(result))
            archive.writestr("report.html", report_html(result))
        os.replace(temp, destination)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
