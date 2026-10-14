"""Small desktop packaging check: 100 rows, five variables, one PC worker."""
import json
import os
import platform
from pathlib import Path


def run(output_path):
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLCONFIGDIR", str(output / "matplotlib"))
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .engine import Settings, read_table, sample_data, temporal_test
    from .ui import MainWindow
    from .report import export_bundle, structure_text, graph_svg
    from .graphics_export import export_png

    # Import the optional discovery backends to catch omitted bundled libraries.
    from lingam import RESIT, VARLiNGAM
    from tigramite.lpcmci import LPCMCI
    temporal_test(Settings(temporal_test="gpdc", shuffle_samples=99))
    temporal_test(Settings(temporal_test="cmiknn", shuffle_samples=99))

    app = QApplication([])
    if platform.system() == "Windows":
        from PySide6.QtGui import QFontDatabase
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"))
    window = MainWindow()
    window.show()
    stage = [0]
    status = {"ok": False, "rows": 100, "variables": 5, "platform": platform.platform(),
              "architecture": platform.machine(), "errors": []}

    def finish(message=None):
        timer.stop()
        if message:
            status["errors"].append(str(message))
        status["ok"] = not status["errors"] and stage[0] == 2
        (output / "smoke.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        app.exit(0 if status["ok"] else 1)

    window.error = lambda message, detail=None: finish(message)

    def tick():
        try:
            if stage[0] == 0:
                frame = sample_data("observational").head(100)
                for suffix in ("csv", "xlsx", "dta"):
                    path = output / ("sample." + suffix)
                    if suffix == "dta":
                        frame.to_stata(path, write_index=False, version=118)
                    elif suffix == "xlsx":
                        frame.to_excel(path, index=False)
                    else:
                        frame.to_csv(path, index=False, encoding="utf-8-sig")
                    loaded = read_table(str(path))
                    assert loaded.shape == (100, 5) and list(loaded) == list(frame)
                window.set_data(loaded, {"name": "小样本 Stata 自检"})
                assert len(window.selected_columns()) == 5
                window.run_analysis()
                stage[0] = 1
            elif stage[0] == 1 and window.process is None and not window.pending:
                assert len(window.history) == 1
                result = window.history[0]
                assert result["rows_used"] == 100 and result["settings"]["algorithm"] == "pc"
                window.show_result(result)
                node = window.graph.nodes[result["columns"][0]]
                node.setPos(node.x() + 30, node.y() + 20)
                assert "graph_layout" in result
                export_png(output / "graph.png", result)
                (output / "graph.svg").write_text(graph_svg(result), encoding="utf-8")
                (output / "structure.txt").write_text(structure_text(result), encoding="utf-8-sig")
                export_bundle(str(output / "result.zip"), result)
                app.processEvents()
                window.grab().save(str(output / "desktop.png"))
                status["edges"] = len(result["edges"])
                stage[0] = 2
                finish()
        except Exception as exc:
            finish(exc)

    timer = QTimer()
    timer.setInterval(200)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(180_000, lambda: finish("Small-sample check timed out"))
    return app.exec()
