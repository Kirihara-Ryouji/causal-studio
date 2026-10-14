from __future__ import annotations

import json
import multiprocessing as mp
import queue
from dataclasses import replace
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QByteArray, QTimer, Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget, QSizePolicy,
    QGraphicsEllipseItem, QGraphicsSimpleTextItem, QGraphicsItem, QLineEdit, QListWidget, QListWidgetItem, QListView, QMenu)

from .engine import Settings, analysis_worker, file_hash, profile, read_table, sample_data
from .report import KIND_LABELS, export_bundle, graph_svg, graph_geometry, value_text, structure_text
from .graphics_export import export_png
from .fonts import UI_FONT, TEXT_FONT

ALGORITHMS = {
    "pc": ("PC", "条件独立检验。适合独立样本，输出有向及未定向关系；假设没有潜在共同原因。"),
    "fci": ("FCI", "允许潜在共同原因，输出 PAG。圆端点表示不确定，双箭头不代表双向因果。"),
    "ges": ("GES", "通过线性高斯 BIC 评分搜索因果等价类。适合连续数据，不使用显著性 α。"),
    "lingam": ("DirectLiNGAM", "线性、非高斯、独立噪声模型。输出方向与标准化系数；高斯数据不满足其识别条件。"),
    "resit": ("RESIT · 非线性", "随机森林回归 + HSIC。适合连续变量的非线性加性噪声模型，无潜在共同原因。最多 100,000 行、30 个变量；大样本内存和耗时可能很高，可取消。"),
    "pcmci": ("PCMCI", "搜索滞后关系，采用 BH-FDR。可选择线性或非线性检验，需要等间隔、平稳的单条时间序列。"),
    "pcmci_plus": ("PCMCI+", "同时发现同期和滞后关系，保留同期未定向边；可选择非线性检验，不作 FDR 校正。"),
    "varlingam": ("VARLiNGAM", "线性非高斯时间序列，同期无环。最大滞后用作固定 VAR 阶数；显示标准化结构系数，不使用 α。"),
    "lpcmci": ("LPCMCI · 实验性", "允许未观测共同原因的时间序列 PAG。圆端点为不确定，双箭头表示潜在混杂；不作 FDR 校正。"),
}

STYLE = """
QMainWindow, QWidget { background: #f3f6f8; color: #173343; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 25px; font-weight: 700; color: #133c47; }
QLabel#title { font-size: 27px; font-weight: 700; }
QLabel#stat { font-size: 26px; font-weight: 600; }
QLabel#muted { color: #677f8f; }
QLabel#step { color: #21827d; font-weight: 700; font-size: 14px; padding: 8px 0; }
QLabel#notice { background: #e5f2f0; color: #26675f; border-radius: 8px; padding: 12px; }
QFrame#card { background: white; border: 1px solid #dce5ea; border-radius: 12px; }
QPushButton { background: white; border: 1px solid #cbdbe2; border-radius: 7px; padding: 9px 14px; font-weight: 500; }
QPushButton:hover { border-color: #248c87; background: #eff9f7; }
QPushButton#primary { background: #167b76; color: white; border-color: #167b76; font-weight: 600; }
QPushButton#primary:hover { background: #106963; }
QPushButton:disabled { color: #97aab4; background: #eaf0f3; border-color: #dde6eb; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: white; border: 1px solid #cbdbe2; border-radius: 6px; padding: 7px; min-height: 20px; }
QListWidget { background: white; border: 1px solid #dce5ea; border-radius: 7px; }
QListWidget::item { background: #e5f2f0; color: #26675f; border-radius: 5px; padding: 6px; margin: 3px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #d7eeea; }
QTableWidget { background: white; alternate-background-color: #f6f9fa; border: none; gridline-color: #e5ecef; selection-background-color: #deeeec; selection-color: #173343; }
QHeaderView::section { background: #edf3f5; color: #577080; padding: 9px; border: none; border-bottom: 1px solid #dce5ea; }
QTabWidget::pane { border: 1px solid #dce5ea; border-radius: 8px; background: white; }
QTabBar::tab { padding: 12px 20px; color: #657f8d; margin-right: 4px; }
QTabBar::tab:selected { color: #167b76; background: white; border-bottom: 3px solid #167b76; }
QTextBrowser { background: white; border: none; padding: 14px; }
QProgressBar { border: none; border-radius: 3px; background: #dceae8; height: 5px; }
QProgressBar::chunk { background: #248c87; }
QScrollArea { border: none; }
QSplitter::handle { background: #e3ebef; }
QCheckBox { spacing: 8px; }
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName("primary")
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.verticalHeader().setVisible(False)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def populate(widget, rows):
    widget.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            widget.setItem(i, j, item)


class VariableNode(QGraphicsEllipseItem):
    def __init__(self, name, position, owner):
        super().__init__(-91, -31, 182, 62)
        self.name, self.owner = name, owner
        self.setBrush(QBrush(QColor('white')))
        self.setPen(QPen(QColor('#9dbfc5'), 2))
        self.setPos(*position)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(name + '\n按住左键拖动节点；只调整布局，不改变因果结果。')
        text = QGraphicsSimpleTextItem(name if len(name) <= 12 else name[:11]+'…', self)
        text.setFont(QFont(TEXT_FONT, 10))
        text.setBrush(QBrush(QColor('#173343')))
        text.setPos(-text.boundingRect().width()/2, -text.boundingRect().height()/2)
        text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.owner.node_moved(self.name, self.pos())
        return super().itemChange(change, value)


class GraphView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#f8fafc"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.renderer = None
        self.result = None
        self.nodes = {}

    def display(self, result):
        self.scene().clear()
        self.nodes = {}
        self.result = result
        if self.renderer:
            self.renderer.deleteLater()
        self.renderer = QSvgRenderer(self)
        self.background = QGraphicsSvgItem()
        self.background.setSharedRenderer(self.renderer)
        self.background.setZValue(-1)
        self.background.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene().addItem(self.background)
        self.redraw_edges()
        positions, _ = graph_geometry(result)
        for name, position in positions.items():
            node = VariableNode(name, position, self)
            self.scene().addItem(node)
            self.nodes[name] = node
        self.fit()

    def redraw_edges(self):
        self.renderer.load(QByteArray(graph_svg(self.result, include_nodes=False).encode('utf-8')))
        self.background.setSharedRenderer(self.renderer)
        _, (x, y, w, h) = graph_geometry(self.result)
        self.background.setPos(x, y)
        self.scene().setSceneRect(QRectF(x, y, w, h))
        self.viewport().update()

    def node_moved(self, name, point):
        self.result.setdefault('graph_layout', {})[name] = [point.x(), point.y()]
        self.redraw_edges()

    def reset_layout(self):
        if self.result is not None:
            self.result.pop('graph_layout', None)
            self.display(self.result)

    def fit(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        if .08 <= self.transform().m11()*factor <= 6:
            self.scale(factor, factor)
        event.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.frame = None
        self.source = {}
        self.history = []
        self.current_result = None
        self.process = None
        self.message_queue = None
        self.pending = []
        self.batch_columns = []
        self.setWindowTitle("Causal Studio · 因果发现工作台")
        self.resize(1440, 930)
        self.setMinimumSize(1100, 740)
        self.setStyleSheet(STYLE.replace("Microsoft YaHei UI", UI_FONT))
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter()
        outer.addWidget(splitter)

        self.controls = QWidget()
        side = QVBoxLayout(self.controls)
        side.setContentsMargins(25, 22, 25, 22)
        side.setSpacing(12)
        side.addWidget(label("Causal Studio", "brand"))
        side.addWidget(label("因果发现工作台  /  0.5", "muted"))
        side.addWidget(label("01   数据与任务", "step"))
        self.mode = QComboBox()
        self.mode.addItem("普通观测数据 · 独立样本", "observational")
        self.mode.addItem("时间序列 · 单条等间隔序列", "timeseries")
        side.addWidget(self.mode)
        self.import_button = button("导入表格  CSV / Excel / Stata", self.import_data, True)
        side.addWidget(self.import_button)
        side.addWidget(button("载入当前模式示例", self.load_sample))
        self.file_label = label("尚未载入数据", "muted", True)
        side.addWidget(self.file_label)
        side.addWidget(label("02   算法与参数", "step"))
        self.algorithm = QComboBox()
        side.addWidget(self.algorithm)
        self.algorithm_hint = label("", "notice", True)
        side.addWidget(self.algorithm_hint)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.test = QComboBox()
        self.test.addItem("连续 · Fisher-Z", "fisherz")
        self.test.addItem("离散 · G²", "gsq")
        form.addRow("数据检验", self.test)
        self.temporal_test = QComboBox()
        for title, key in [("线性 · ParCorr", "parcorr"), ("非线性 · GPDC", "gpdc"), ("非线性 · CMIknn", "cmiknn")]:
            self.temporal_test.addItem(title, key)
        self.temporal_test.setToolTip("GPDC：加性噪声；CMIknn：更一般的非线性依赖。非线性计算较慢，最多 100,000 行、30 个变量；大样本内存和耗时可能很高，可取消。")
        form.addRow("时序检验", self.temporal_test)
        self.shuffle_samples = QSpinBox()
        self.shuffle_samples.setRange(99, 9999)
        self.shuffle_samples.setValue(199)
        self.shuffle_samples.setSingleStep(100)
        self.shuffle_samples.setToolTip("非线性检验使用。次数越多，p 值分辨率越细，计算越慢；BH-FDR 可能需要更多次数。")
        form.addRow("重采样次数", self.shuffle_samples)
        self.temporal_test.currentIndexChanged.connect(self.algorithm_changed)
        self.alpha = QDoubleSpinBox()
        self.alpha.setDecimals(3)
        self.alpha.setRange(.001, .2)
        self.alpha.setSingleStep(.005)
        self.alpha.setValue(.01)
        form.addRow("阈值 α", self.alpha)
        self.coefficient = QDoubleSpinBox()
        self.coefficient.setRange(0, 10)
        self.coefficient.setSingleStep(.05)
        self.coefficient.setValue(.1)
        form.addRow("系数绝对值阈值", self.coefficient)
        self.lag = QSpinBox()
        self.lag.setRange(1, 20)
        self.lag.setValue(3)
        form.addRow("最大滞后步长", self.lag)
        self.time_column = QComboBox()
        self.time_column.addItem("不指定时间列", None)
        form.addRow("时间列", self.time_column)
        self.missing = QComboBox()
        self.missing.addItem("发现缺失时停止", "reject")
        self.missing.addItem("仅使用完整行（独立样本）", "drop")
        form.addRow("缺失值处理", self.missing)
        side.addLayout(form)
        self.parameter_form = form
        self.row_confirm = QCheckBox("确认行顺序为等间隔时间顺序")
        side.addWidget(self.row_confirm)
        side.addWidget(label("03   运行与导出", "step"))
        self.run_button = button("运行因果发现", self.run_analysis, True)
        side.addWidget(self.run_button)
        self.compare_button = button("依次运行同类算法作对照", self.run_comparison)
        side.addWidget(self.compare_button)
        side.addWidget(label("对照保留各算法假设；一致性不等于因果证据。", "muted", True))
        side.addStretch()
        side.addWidget(label("本机计算 · 无需账号 · 数据不上传", "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.controls)
        scroll.setMinimumWidth(330)
        splitter.addWidget(scroll)

        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(28, 22, 28, 20)
        main.setSpacing(14)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("从数据，探索因果结构", "title"))
        titles.addWidget(label("导入表格 → 选择变量与算法 → 检查候选关系", "muted"))
        head.addLayout(titles)
        head.addStretch()
        self.export_button = button("导出结果包", self.export_result)
        self.export_button.setEnabled(False)
        head.addWidget(self.export_button)
        main.addLayout(head)
        stats = QHBoxLayout()
        self.stats = []
        for title in ("样本行", "分析变量", "候选关系", "已完成分析"):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(17, 12, 17, 12)
            box.addWidget(label(title, "muted"))
            number = label("—", "stat")
            number.setFont(QFont(UI_FONT, 23, QFont.Weight.DemiBold))
            box.addWidget(number)
            self.stats.append(number)
            stats.addWidget(card)
        main.addLayout(stats)
        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)

        data_page = QWidget()
        self.data_page = data_page
        data_box = QVBoxLayout(data_page)
        data_box.addWidget(label("勾选分析变量；ID、时间索引和常数列通常应排除。上限 30 个变量。", "muted", True))
        filters = QHBoxLayout()
        self.variable_search = QLineEdit()
        self.variable_search.setPlaceholderText('搜索变量名称；空格分隔多个关键词')
        self.variable_search.setClearButtonEnabled(True)
        self.variable_filter = QComboBox()
        self.variable_filter.addItems(['全部变量', '数值变量', '文本 / 类别', '含缺失值', '已选变量', '常数 / 空列'])
        filters.addWidget(self.variable_search, 1)
        filters.addWidget(self.variable_filter)
        data_box.addLayout(filters)
        selection = QHBoxLayout()
        selection.addWidget(button("选中筛选结果", lambda: self.select_visible(True)))
        selection.addWidget(button("取消筛选结果", lambda: self.select_visible(False)))
        selection.addWidget(button("只选数值变量", self.select_numeric))
        selection.addWidget(button("清空选择", self.clear_selection))
        selection.addStretch()
        data_box.addLayout(selection)
        self.columns = table(["分析", "变量名", "识别类型", "缺失数", "不同取值"])
        self.columns.itemChanged.connect(self.selection_changed)
        self.columns.setMaximumHeight(280)
        data_box.addWidget(self.columns)
        self.selection_summary = label('已选 0 / 30 个变量；点击下方标签可移除。', 'muted', True)
        data_box.addWidget(self.selection_summary)
        self.selected_tags = QListWidget()
        self.selected_tags.setViewMode(QListView.ViewMode.IconMode)
        self.selected_tags.setResizeMode(QListView.ResizeMode.Adjust)
        self.selected_tags.setMovement(QListView.Movement.Static)
        self.selected_tags.setMaximumHeight(85)
        self.selected_tags.itemClicked.connect(self.remove_tag)
        data_box.addWidget(self.selected_tags)
        self.variable_search.textChanged.connect(self.filter_variables)
        self.variable_filter.currentIndexChanged.connect(self.filter_variables)
        data_box.addWidget(label("数据预览 · 最多显示前 100 行", "muted"))
        self.preview = table([])
        data_box.addWidget(self.preview, 1)
        self.tabs.addTab(data_page, "数据与变量")

        graph_page = QWidget()
        graph_box = QVBoxLayout(graph_page)
        graph_toolbar = QHBoxLayout()
        self.result_title = label("载入示例并运行，开始探索", "muted")
        graph_toolbar.addWidget(self.result_title, 1)
        self.graph = GraphView()
        graph_toolbar.addWidget(button("适应窗口", self.graph.fit))
        graph_toolbar.addWidget(button("重置布局", self.graph.reset_layout))
        graph_export = QPushButton('导出图与文本')
        export_menu = QMenu(graph_export)
        export_menu.addAction('结构图 · PNG 图片', lambda: self.export_structure('png'))
        export_menu.addAction('结构图 · SVG 矢量图', self.export_svg)
        export_menu.addAction('结构文本 · TXT 文件', lambda: self.export_structure('txt'))
        export_menu.addAction('复制结构文本', self.copy_structure)
        graph_export.setMenu(export_menu)
        graph_toolbar.addWidget(graph_export)
        graph_box.addLayout(graph_toolbar)
        graph_box.addWidget(self.graph, 1)
        graph_box.addWidget(label("拖动节点调整位置 · 拖动空白处平移 · 滚轮缩放 · 导出保留布局；拖动不改变因果关系", "muted", True))
        self.tabs.addTab(graph_page, "因果关系图")
        self.edges = table(["源变量", "关系类型", "目标变量", "滞后", "统计量 / 系数", "p 值", "q 值"])
        self.tabs.addTab(self.edges, "关系明细")
        self.explanation = QTextBrowser()
        self.explanation.setPlainText("分析完成后，这里将展示算法假设、缺失值处理、样本数量及版本记录。")
        self.tabs.addTab(self.explanation, "分析说明")

        history_page = QWidget()
        history_box = QVBoxLayout(history_page)
        history_box.addWidget(label("点击历史查看或导出结果。变量集合或处理方式不同时，结果不能直接比较；对照不代表真值。更换数据将清空历史，请先导出需要保留的结果。", "muted", True))
        self.history_table = table(["运行", "算法", "样本", "关系", "耗时 / 秒"])
        self.history_table.setMaximumHeight(200)
        self.history_table.cellClicked.connect(self.show_history)
        history_box.addWidget(self.history_table)
        self.comparison_table = table(["源变量", "目标变量", "滞后", "各次分析中的关系"])
        history_box.addWidget(self.comparison_table, 1)
        self.tabs.addTab(history_page, "历史与对照")

        self.notice = label("候选因果关系需要结合领域知识与研究设计验证；算法无法仅凭任意表格保证真实因果。", "notice", True)
        main.addWidget(self.notice)
        status = QHBoxLayout()
        self.status = label("就绪 · 支持 CSV、TSV、XLSX、DTA · 100,000 行 / 30 个分析变量", "muted")
        status.addWidget(self.status, 1)
        self.cancel_button = button("取消计算", self.cancel)
        self.cancel_button.setEnabled(False)
        status.addWidget(self.cancel_button)
        main.addLayout(status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.hide()
        main.addWidget(self.progress)
        splitter.addWidget(content)
        splitter.setSizes([360, 1080])
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.algorithm.currentIndexChanged.connect(self.algorithm_changed)
        self.time_column.currentIndexChanged.connect(self.time_changed)
        for combo in self.controls.findChildren(QComboBox):
            combo.setMinimumContentsLength(10)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mode_changed()

    def mode_changed(self):
        temporal = self.mode.currentData() == "timeseries"
        self.algorithm.blockSignals(True)
        self.algorithm.clear()
        for key in (("pcmci", "pcmci_plus", "varlingam", "lpcmci") if temporal else ("pc", "fci", "ges", "lingam", "resit")):
            self.algorithm.addItem(ALGORITHMS[key][0], key)
        self.algorithm.blockSignals(False)
        self.lag.setEnabled(temporal)
        self.time_column.setEnabled(temporal)
        self.row_confirm.setEnabled(temporal)
        self.missing.setEnabled(not temporal)
        self.algorithm_changed()
        self.time_changed()

    def algorithm_changed(self):
        key = self.algorithm.currentData()
        if not key:
            return
        self.algorithm_hint.setText(ALGORITHMS[key][1])
        self.test.setEnabled(key in ("pc", "fci"))
        self.test.setItemText(0, {"pcmci": "见时序检验", "pcmci_plus": "见时序检验",
                                  "ges": "连续 · 高斯 BIC", "lingam": "连续 · 非高斯", "resit": "连续 · HSIC", "varlingam": "连续 · 非高斯", "lpcmci": "见时序检验"}.get(key, "连续 · Fisher-Z"))
        if key not in ("pc", "fci"):
            self.test.setCurrentIndex(0)
        self.alpha.setEnabled(key not in ("ges", "lingam", "varlingam"))
        self.coefficient.setEnabled(key in ("lingam", "varlingam"))
        temporal = key in ("pcmci", "pcmci_plus", "lpcmci")
        self.temporal_test.setEnabled(temporal)
        self.shuffle_samples.setEnabled(temporal and self.temporal_test.currentData() != "parcorr")
        for control, visible in [(self.test, key in ("pc", "fci")),
                                 (self.temporal_test, temporal),
                                 (self.shuffle_samples, temporal and self.temporal_test.currentData() != "parcorr"),
                                 (self.coefficient, key in ("lingam", "varlingam")),
                                 (self.alpha, key not in ("ges", "lingam", "varlingam")),
                                 (self.lag, self.mode.currentData() == "timeseries"),
                                 (self.time_column, self.mode.currentData() == "timeseries"),
                                 (self.missing, self.mode.currentData() == "observational")]:
            self.parameter_form.setRowVisible(control, visible)
        self.row_confirm.setVisible(self.mode.currentData() == "timeseries")

    def time_changed(self):
        if self.mode.currentData() == "timeseries":
            chosen_time = self.time_column.currentData()
            for i in range(self.columns.rowCount()):
                if self.columns.item(i, 1).text() == chosen_time:
                    self.columns.item(i, 0).setCheckState(Qt.CheckState.Unchecked)

    def selection_changed(self, item=None):
        if item is not None and item.column() == 0 and item.checkState() == Qt.CheckState.Checked:
            name = self.columns.item(item.row(), 1).text()
            blocked = self.mode.currentData() == 'timeseries' and name == self.time_column.currentData()
            if blocked or len(self.selected_columns()) > 30:
                self.columns.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.columns.blockSignals(False)
                self.status.setText('时间列不能作为分析变量。' if blocked else '最多选择 30 个变量，请先移除其他变量。')
        selected = self.selected_columns()
        self.stats[1].setText(str(len(selected)))
        self.selected_tags.clear()
        for name in selected:
            tag = QListWidgetItem(name + '  ×')
            tag.setData(Qt.ItemDataRole.UserRole, name)
            tag.setToolTip('点击移除：' + name)
            self.selected_tags.addItem(tag)
        self.filter_variables()

    def filter_variables(self, *_):
        terms = self.variable_search.text().casefold().split()
        kind = self.variable_filter.currentIndex()
        shown = 0
        for i in range(self.columns.rowCount()):
            name = self.columns.item(i, 1).text()
            numeric = self.columns.item(i, 2).text() == '数值'
            missing = int(self.columns.item(i, 3).text())
            unique = int(self.columns.item(i, 4).text())
            checked = self.columns.item(i, 0).checkState() == Qt.CheckState.Checked
            matches = (not terms or any(t in name.casefold() for t in terms)) and (
                kind == 0 or kind == 1 and numeric or kind == 2 and not numeric or
                kind == 3 and missing > 0 or kind == 4 and checked or kind == 5 and unique <= 1)
            self.columns.setRowHidden(i, not matches)
            shown += int(matches)
        self.selection_summary.setText(f'显示 {shown} / {self.columns.rowCount()} 个变量 · 已选 {len(self.selected_columns())} / 30；点击标签移除。筛选不会清除已有选择。')

    def select_visible(self, checked):
        rows = [i for i in range(self.columns.rowCount()) if not self.columns.isRowHidden(i)]
        for i in rows:
            if int(self.columns.item(i, 4).text()) > 1 or not checked:
                self.columns.item(i, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def remove_tag(self, tag):
        name = tag.data(Qt.ItemDataRole.UserRole)
        for i in range(self.columns.rowCount()):
            if self.columns.item(i, 1).text() == name:
                self.columns.item(i, 0).setCheckState(Qt.CheckState.Unchecked)
                return

    def selected_columns(self):
        return [self.columns.item(i, 1).text() for i in range(self.columns.rowCount())
                if self.columns.item(i, 0).checkState() == Qt.CheckState.Checked]

    def select_numeric(self):
        if self.frame is None:
            return
        self.clear_selection()
        for i, item in enumerate(profile(self.frame)):
            checked = item["eligible"] and not (self.mode.currentData() == "timeseries" and item["name"] == self.time_column.currentData())
            self.columns.item(i, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def clear_selection(self):
        for i in range(self.columns.rowCount()):
            self.columns.item(i, 0).setCheckState(Qt.CheckState.Unchecked)

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入表格", "", "表格 (*.csv *.tsv *.xlsx *.dta)")
        if not path:
            return
        try:
            sheet = 0
            if Path(path).suffix.lower() == ".xlsx":
                with pd.ExcelFile(path) as workbook:
                    if len(workbook.sheet_names) > 1:
                        sheet, ok = QInputDialog.getItem(self, "选择工作表", "工作表", workbook.sheet_names, editable=False)
                        if not ok:
                            return
                    else:
                        sheet = workbook.sheet_names[0]
            frame = read_table(path, sheet)
            self.set_data(frame, {"name": Path(path).name, "sheet": sheet, "sha256": file_hash(path),
                                  **({"stata_metadata": frame.attrs["stata_metadata"]} if "stata_metadata" in frame.attrs else {})})
        except Exception as exc:
            self.error(str(exc))

    def load_sample(self):
        mode = self.mode.currentData()
        frame = sample_data(mode)
        self.set_data(frame, {"name": "时间序列模拟示例" if mode == "timeseries" else "独立样本模拟示例", "seed": 2026,
                              "note": "示例为线性高斯模型，适合 PC/FCI/GES/PCMCI；不满足 DirectLiNGAM / VARLiNGAM 非高斯假设，也不适合验证 RESIT 非线性方向识别。"})
        if mode == "timeseries":
            self.time_column.setCurrentIndex(self.time_column.findData("时间"))

    def set_data(self, frame, source):
        self.frame, self.source = frame, source
        self.history.clear()
        self.current_result = None
        self.export_button.setEnabled(False)
        self.file_label.setText(f"{source['name']}\n{len(frame):,} 行 · {len(frame.columns)} 列")
        self.columns.blockSignals(True)
        details = profile(frame)
        populate(self.columns, [("", r["name"], r["type"], r["missing"], r["unique"]) for r in details])
        selected_count = 0
        for i, info in enumerate(details):
            item = self.columns.item(i, 0)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chosen = info['eligible'] and selected_count < 30
            selected_count += int(chosen)
            item.setCheckState(Qt.CheckState.Checked if chosen else Qt.CheckState.Unchecked)
        self.columns.blockSignals(False)
        self.variable_search.clear()
        self.variable_filter.setCurrentIndex(0)
        self.time_column.clear()
        self.time_column.addItem("不指定时间列", None)
        for name in frame.columns:
            self.time_column.addItem(name, name)
        self.row_confirm.setChecked(False)
        self.preview.setColumnCount(len(frame.columns))
        self.preview.setHorizontalHeaderLabels(list(frame.columns))
        populate(self.preview, [["∅" if pd.isna(v) else f"{v:.6g}" if isinstance(v, float) else str(v)[:120] for v in row]
                                for row in frame.head(100).itertuples(index=False, name=None)])
        self.edges.setRowCount(0)
        self.history_table.setRowCount(0)
        self.comparison_table.setRowCount(0)
        self.graph.scene().clear()
        self.graph.nodes = {}
        self.graph.result = None
        self.result_title.setText("数据已载入，等待分析")
        self.explanation.setPlainText("选择变量及算法后运行。" + source.get("note", ""))
        self.stats[0].setText(f"{len(frame):,}")
        self.stats[2].setText("—")
        self.stats[3].setText("0")
        self.selection_changed()
        self.tabs.setCurrentIndex(0)
        self.status.setText("数据已载入 · 请检查所选变量")

    def settings(self):
        key = self.algorithm.currentData()
        return Settings(mode=self.mode.currentData(), algorithm=key,
                        test=self.test.currentData() if key in ("pc", "fci") else "fisherz",
                        alpha=self.alpha.value(), max_lag=self.lag.value(),
                        missing=self.missing.currentData() if self.mode.currentData() == "observational" else "reject",
                        time_column=self.time_column.currentData() if self.mode.currentData() == "timeseries" else None,
                        row_order_confirmed=self.row_confirm.isChecked(), coefficient_threshold=self.coefficient.value(),
                        temporal_test=self.temporal_test.currentData(), shuffle_samples=self.shuffle_samples.value())

    def run_analysis(self):
        self.begin([self.settings()])

    def run_comparison(self):
        cfg = self.settings()
        keys = ("pcmci", "pcmci_plus", "varlingam", "lpcmci") if cfg.mode == "timeseries" else (("pc", "fci") if cfg.test == "gsq" else ("pc", "fci", "ges", "lingam", "resit"))
        self.begin([replace(cfg, algorithm=key) for key in keys])

    def begin(self, configs):
        if self.frame is None:
            self.error("请先导入表格或载入示例。")
            return
        if not 2 <= len(self.selected_columns()) <= 30:
            self.error("请选择 2–30 个分析变量。")
            return
        self.batch_columns = self.selected_columns()
        self.pending = configs
        self.controls.setEnabled(False)
        self.data_page.setEnabled(False)
        self.columns.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.launch_next()

    def launch_next(self):
        cfg = self.pending.pop(0)
        self.active_cfg = cfg
        context = mp.get_context("spawn")
        self.message_queue = context.Queue()
        self.process = context.Process(target=analysis_worker, args=(self.message_queue, self.frame,
                                          self.batch_columns, cfg, self.source), daemon=True)
        self.dead_polls = 0
        try:
            self.process.start()
        except Exception as exc:
            self.pending = []
            self.process = None
            self.finish()
            self.error(str(exc))
            return
        self.status.setText(f"{ALGORITHMS[cfg.algorithm][0]} · 启动计算进程…")
        self.timer.start()

    def poll(self):
        if self.message_queue is None:
            return
        try:
            while True:
                message = self.message_queue.get_nowait()
                if message[0] == "progress":
                    self.status.setText(f"{ALGORITHMS[self.active_cfg.algorithm][0]} · {message[1]}")
                elif message[0] == "result":
                    result = message[1]
                    self.history.append(result)
                    self.show_result(result)
                    self.update_history()
                    self.stop_process()
                    if self.pending:
                        self.launch_next()
                    else:
                        self.finish()
                        self.status.setText(f"分析完成 · {len(result['edges'])} 条候选关系 · {result['elapsed_seconds']:.2f} 秒")
                    return
                elif message[0] == "error":
                    self.pending = []
                    self.stop_process()
                    self.finish()
                    self.status.setText("分析停止 · 请检查提示后重试")
                    self.error(message[1], message[2])
                    return
        except queue.Empty:
            if self.process is not None and self.process.exitcode is not None:
                self.dead_polls += 1
                if self.dead_polls < 3:
                    return
                code = self.process.exitcode
                self.pending = []
                self.stop_process()
                self.finish()
                self.error(f"计算进程意外退出（代码 {code}），请减少变量后重试。")

    def stop_process(self):
        self.timer.stop()
        if self.process is not None:
            self.process.join(timeout=.3)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
            self.process.close()
            self.process = None
        if self.message_queue is not None:
            self.message_queue.close()
            self.message_queue = None

    def finish(self):
        self.data_page.setEnabled(True)
        self.controls.setEnabled(True)
        self.columns.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.hide()

    def cancel(self):
        self.pending = []
        self.stop_process()
        self.finish()
        self.status.setText("已取消计算 · 已完成的分析仍保留在历史中")

    def show_result(self, result):
        self.current_result = result
        self.status.setText(f"正在查看 {result['algorithm']} · {len(result['edges'])} 条候选关系 · {result['elapsed_seconds']:.2f} 秒")
        self.export_button.setEnabled(True)
        self.result_title.setText(result["algorithm"] + " · " + result["source"].get("name", ""))
        self.graph.display(result)
        populate(self.edges, [(e["source"], KIND_LABELS[e["kind"]], e["target"], e["lag"],
                              value_text(e["statistic"]), value_text(e["p_value"]), value_text(e["q_value"])) for e in result["edges"]])
        explanation = [result["algorithm"], "", f"原始样本：{result['rows_original']}   有效样本：{result['rows_used']}   删除行：{result['rows_removed']}",
                       "", "算法假设与结果解释", *["• " + s for s in result["assumptions"]], "", "数据处理记录",
                       *["• " + s for s in result["notes"]], result["source"].get("note", ""), "", "配置与版本",
                       json.dumps({"settings": result["settings"], "versions": result["versions"], "source": result["source"]}, ensure_ascii=False, indent=2)]
        self.explanation.setPlainText("\n".join(explanation))
        for widget, text in zip(self.stats, (f"{result['rows_used']:,}", str(len(result["columns"])), str(len(result["edges"])), str(len(self.history)))):
            widget.setText(text)
        self.tabs.setCurrentIndex(1)
        QTimer.singleShot(0, self.graph.fit)

    def update_history(self):
        populate(self.history_table, [(i+1, r["algorithm"], r["rows_used"], len(r["edges"]), r["elapsed_seconds"])
                                      for i, r in enumerate(self.history)])
        comparisons = {}
        for i, result in enumerate(self.history):
            for edge in result["edges"]:
                # Canonical pair at lag zero; retain the actual arrow direction in the label.
                a, b = (sorted((edge["source"], edge["target"])) if edge["lag"] == 0 else (edge["source"], edge["target"]))
                key = (a, b, edge["lag"])
                comparisons.setdefault(key, []).append(f"#{i+1} {edge['source']} {KIND_LABELS[edge['kind']]} {edge['target']}")
        populate(self.comparison_table, [(a, b, lag, "  |  ".join(values)) for (a, b, lag), values in comparisons.items()])

    def show_history(self, row, _column):
        self.show_result(self.history[row])

    def export_result(self):
        if self.current_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存结果包", "causal-result.zip", "ZIP 结果包 (*.zip)")
        if path:
            try:
                export_bundle(path, self.current_result)
                self.status.setText("已导出 SVG 结构图、TXT 结构文本、报告、关系明细及配置（不含原始数据）")
            except Exception as exc:
                self.error(str(exc))

    def export_svg(self):
        self.export_structure('svg')

    def copy_structure(self):
        if self.current_result is None:
            self.error('请先运行分析。')
            return
        QApplication.clipboard().setText(structure_text(self.current_result))
        self.status.setText('结构文本已复制，可粘贴到 Word、记事本或其他应用。')

    def export_structure(self, kind):
        if self.current_result is None:
            self.error("请先运行分析。")
            return
        filters = {'svg':'SVG 矢量图 (*.svg)', 'png':'PNG 图片 (*.png)', 'txt':'结构文本 (*.txt)'}
        path, _ = QFileDialog.getSaveFileName(self, "导出因果结构", 'causal-structure.' + kind, filters[kind])
        if path:
            try:
                if not Path(path).suffix:
                    path += '.' + kind
                if kind == 'png':
                    export_png(path, self.current_result)
                else:
                    Path(path).write_text(structure_text(self.current_result) if kind == 'txt' else graph_svg(self.current_result),
                                          encoding='utf-8-sig' if kind == 'txt' else 'utf-8')
                self.status.setText(kind.upper() + ' 因果结构已保存：' + path)
            except Exception as exc:
                self.error(str(exc))

    def error(self, message, detail=None):
        box = QMessageBox(self)
        box.setWindowTitle("请检查分析设置")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(message)
        if detail:
            box.setDetailedText(detail)
        box.exec()

    def closeEvent(self, event):
        self.pending = []
        self.stop_process()
        event.accept()


def main():
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("Causal Studio")
    application.setFont(QFont(UI_FONT, 10))
    window = MainWindow()
    window.show()
    return application.exec()
