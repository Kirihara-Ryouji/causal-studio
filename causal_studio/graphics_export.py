from pathlib import Path
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from .report import graph_svg


def export_png(path, result):
    """Render the entire laid-out graph, independent of viewport pan/zoom."""
    renderer = QSvgRenderer(QByteArray(graph_svg(result).encode('utf-8')))
    if not renderer.isValid():
        raise ValueError('结构图无法渲染，请重置布局后重试。')
    bounds = renderer.viewBoxF()
    scale = min(2.0, 4096 / max(bounds.width(), bounds.height()))
    width, height = max(1, round(bounds.width()*scale)), max(1, round(bounds.height()*scale))
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0,0,width,height))
    finally:
        painter.end()
    if not image.save(str(Path(path)), 'PNG'):
        raise OSError('无法保存 PNG，请检查目标路径或文件是否被占用。')
