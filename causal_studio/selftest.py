"""Exercise the real Qt workflow, including Windows spawned computation workers."""
import json
import os
import numpy as np
import pandas as pd
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from .report import export_bundle, structure_text
from .graphics_export import export_png
from .engine import Settings, prepare, read_table, sample_data
from .ui import MainWindow


def run(output_path):
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('MPLCONFIGDIR', str(output / 'mpl-cache'))
    app = QApplication([])
    for name in ('msyh.ttc', 'segoeui.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name))
    window = MainWindow()
    window.show()
    outcomes = []
    errors = []
    stage = [0]
    scale_checked = [False]

    def error(message, detail=None):
        errors.append({'message': message, 'detail': detail})
        finish()

    def finish():
        timer.stop()
        (output/'selftest.json').write_text(json.dumps({'ok': not errors and len(outcomes) == 15 and scale_checked[0],
                                                      'stata_100000_rows_30_variables': scale_checked[0],
                                                      'results': outcomes, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
        window.close()
        app.exit(1 if errors or len(outcomes) != 15 or not scale_checked[0] else 0)

    def collect():
        for result in window.history:
            key = result['settings']['algorithm']
            if result['settings']['mode'] == 'timeseries':
                key += '-' + result['settings']['temporal_test']
            export_bundle(str(output/f'{key}-result.zip'), result)
            export_png(output/f'{key}-graph.png', result)
            (output/f'{key}-structure.txt').write_text(structure_text(result), encoding='utf-8-sig')
            outcomes.append({'algorithm': key, 'edges': len(result['edges']), 'rows': result['rows_used']})

    def tick():
        try:
            if stage[0] == 0:
                original = sample_data('observational').head(40)
                for suffix in ('csv', 'xlsx', 'dta'):
                    file = output / ('import-check.' + suffix)
                    if suffix == 'csv':
                        original.to_csv(file, index=False, encoding='utf-8-sig')
                    elif suffix == 'dta':
                        original.to_stata(file, write_index=False, version=118)
                    else:
                        original.to_excel(file, index=False)
                    loaded = read_table(str(file))
                    assert loaded.shape == original.shape and list(loaded) == list(original)
                large = pd.DataFrame(np.random.default_rng(48).normal(size=(100000, 30)),
                                     columns=[f'x{i}' for i in range(30)])
                large_path = output/'import-100000x30.dta'
                large.to_stata(large_path, write_index=False, version=118)
                loaded = read_table(str(large_path))
                assert loaded.shape == (100000, 30)
                matrix, *_ = prepare(loaded, list(loaded), Settings(algorithm='resit'))
                assert matrix.shape == (100000, 30)
                scale_checked[0] = True
                del large, loaded, matrix
                window.load_sample()
                window.set_data(window.frame.head(500), window.source)
                window.clear_selection()
                window.variable_search.setText('环境 设备')
                window.select_visible(True)
                assert len(window.selected_columns()) == 2
                window.variable_search.clear()
                window.select_numeric()
                window.grab().save(str(output/'01-data.png'))
                window.run_comparison()
                stage[0] = 1
            elif stage[0] == 1 and window.process is None and not window.pending:
                if len(window.history) != 5:
                    raise RuntimeError('Observation workflow did not complete all five algorithms.')
                collect()
                window.show_result(window.history[0])
                first_node = window.graph.nodes['环境条件']
                first_node.setPos(first_node.x()-100, first_node.y()+80)
                assert 'graph_layout' in window.current_result
                export_bundle(str(output/'custom-layout-result.zip'),window.current_result)
                export_png(output/'custom-layout-graph.png',window.current_result)
                app.processEvents()
                window.grab().save(str(output/'02-pc-graph.png'))
                window.tabs.setCurrentIndex(4)
                app.processEvents()
                window.grab().save(str(output/'03-comparison.png'))
                window.mode.setCurrentIndex(1)
                window.load_sample()
                window.run_comparison()
                stage[0] = 2
            elif stage[0] == 2 and window.process is None and not window.pending:
                if len(window.history) != 4:
                    raise RuntimeError('Time-series workflow did not complete all four algorithms.')
                collect()
                window.show_result(window.history[0])
                app.processEvents()
                window.grab().save(str(output/'04-temporal-graph.png'))
                window.set_data(window.frame.head(150).iloc[:, :3], window.source)
                window.lag.setValue(1)
                window.temporal_test.setCurrentIndex(1)
                window.shuffle_samples.setValue(99)
                window.alpha.setValue(.1)
                configs = [Settings(mode='timeseries', algorithm=key, temporal_test=test, max_lag=1,
                                    shuffle_samples=99, alpha=.1, time_column='时间')
                           for test in ('gpdc', 'cmiknn') for key in ('pcmci', 'pcmci_plus', 'lpcmci')]
                window.begin(configs)
                stage[0] = 3
            elif stage[0] == 3 and window.process is None and not window.pending:
                if len(window.history) != 6:
                    raise RuntimeError('Nonlinear workflow did not complete all six combinations.')
                collect()
                window.show_result(window.history[-1])
                app.processEvents()
                window.grab().save(str(output/'05-nonlinear-graph.png'))
                # Starting and cancelling a worker must leave a usable window.
                window.run_analysis()
                window.cancel()
                assert window.process is None and window.controls.isEnabled()
                finish()
        except Exception as exc:
            errors.append({'message': str(exc)})
            finish()

    window.error = error
    timer = QTimer()
    timer.setInterval(200)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(900_000, lambda: error('Self-test timed out.'))
    return app.exec()
