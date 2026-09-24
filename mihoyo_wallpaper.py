"""从米哈游启动器缓存中提取、预览并下载 WebM 壁纸。"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


CACHE_RELATIVE_PATH = Path("miHoYo/HYP/1/_1/fedata/Cache/Cache/_Data/data_1")
LOGO_PATH = Path(__file__).resolve().parent / "logo.ico"
WINDOWS_APP_ID = "luoriguixi.mihoyo_wallpaper"
PROJECT_URL = "https://github.com/lrgx/miyobg.git"
URL_PATTERN = re.compile(
    rb"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+?\.webm"
    rb"(?=$|[^A-Za-z0-9._~/%-])",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")


def default_cache_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / CACHE_RELATIVE_PATH
    return Path.home() / "AppData/Roaming" / CACHE_RELATIVE_PATH


def extract_webm_urls(data: bytes) -> list[str]:
    """从二进制缓存中提取 URL；缓存的冒号后缀和重复项会被排除。"""
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_PATTERN.finditer(data):
        try:
            raw = match.group().decode("ascii")
            parts = urlsplit(raw)
            if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
                continue
            if not parts.path.lower().endswith(".webm"):
                continue
            # 同一主机的大小写差异不应生成两条结果，路径则保留原样。
            url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
        except (UnicodeDecodeError, ValueError):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def safe_filename(url: str) -> str:
    name = Path(urlsplit(url).path).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name if name.lower().endswith(".webm") else "wallpaper.webm"


class ScanThread(QThread):
    found = Signal(list)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            self.found.emit(extract_webm_urls(self.path.read_bytes()))
        except OSError as exc:
            self.failed.emit(str(exc))


class DownloadThread(QThread):
    progress = Signal(int, int)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, url: str, destination: Path):
        super().__init__()
        self.url = url
        self.destination = destination
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        temp = self.destination.with_name(self.destination.name + ".part")
        try:
            request = urllib.request.Request(
                self.url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "video/webm,*/*"},
            )
            with urllib.request.urlopen(request, timeout=30) as response, temp.open("wb") as output:
                total = int(response.headers.get("Content-Length", "0") or 0)
                received = 0
                while True:
                    if self._cancel_requested:
                        raise InterruptedError()
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                    self.progress.emit(received, total)
            if self._cancel_requested:
                raise InterruptedError()
            temp.replace(self.destination)
            self.completed.emit(str(self.destination))
        except InterruptedError:
            temp.unlink(missing_ok=True)
            self.cancelled.emit()
        except (OSError, urllib.error.URLError, ValueError) as exc:
            temp.unlink(missing_ok=True)
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("米游壁纸提取")
        if LOGO_PATH.is_file():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))
        self.resize(1100, 730)
        self.urls: list[str] = []
        self.scan_thread: ScanThread | None = None
        self.download_thread: DownloadThread | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(10)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("缓存文件"))
        self.path_edit = QLineEdit(str(default_cache_path()))
        self.path_edit.setPlaceholderText("选择 data_1 缓存文件")
        path_row.addWidget(self.path_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self.choose_cache)
        path_row.addWidget(browse)
        self.scan_button = QPushButton("扫描链接")
        self.scan_button.clicked.connect(self.scan)
        path_row.addWidget(self.scan_button)
        layout.addLayout(path_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        search_row = QHBoxLayout()
        self.count_label = QLabel("0 条链接")
        search_row.addWidget(self.count_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("筛选日期或文件名")
        self.search_edit.textChanged.connect(self.filter_rows)
        search_row.addWidget(self.search_edit, 1)
        left_layout.addLayout(search_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["日期", "文件名", "链接"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 260)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        left_layout.addWidget(self.table)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.video = QVideoWidget()
        self.video.setMinimumSize(360, 250)
        right_layout.addWidget(self.video, 1)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.errorOccurred.connect(self.playback_error)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.preview_label = QLabel("选择一条链接后自动预览")
        self.preview_label.setWordWrap(True)
        right_layout.addWidget(self.preview_label)
        controls = QHBoxLayout()
        self.preview_button = QPushButton("预览")
        self.preview_button.clicked.connect(self.preview)
        controls.addWidget(self.preview_button)
        self.pause_button = QPushButton("暂停 / 继续")
        self.pause_button.clicked.connect(self.toggle_playback)
        controls.addWidget(self.pause_button)
        self.browser_button = QPushButton("浏览器打开")
        self.browser_button.clicked.connect(self.open_browser)
        controls.addWidget(self.browser_button)
        right_layout.addLayout(controls)
        self.copy_button = QPushButton("复制下载链接")
        self.copy_button.clicked.connect(self.copy_url)
        right_layout.addWidget(self.copy_button)
        self.download_button = QPushButton("下载选中壁纸…")
        self.download_button.clicked.connect(self.download)
        right_layout.addWidget(self.download_button)
        self.cancel_button = QPushButton("取消下载")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setEnabled(False)
        right_layout.addWidget(self.cancel_button)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)
        splitter.addWidget(right)
        splitter.setSizes([660, 440])

        self.statusBar().showMessage("准备就绪")
        credit_label = QLabel("by 落日归夕  luoriguixi@gmail.com")
        credit_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.statusBar().addPermanentWidget(credit_label)
        self.set_selection_enabled(False)

        copy_action = QAction("复制选中链接", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_url)
        self.addAction(copy_action)

        if default_cache_path().is_file():
            self.scan()

    def choose_cache(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "选择 data_1 文件", self.path_edit.text(), "缓存文件 (data_1);;所有文件 (*)"
        )
        if selected:
            self.path_edit.setText(selected)
            self.scan()

    def scan(self) -> None:
        if self.scan_thread and self.scan_thread.isRunning():
            return
        path = Path(self.path_edit.text().strip())
        if not path.is_file():
            QMessageBox.warning(self, "找不到缓存", f"文件不存在：\n{path}")
            return
        self.scan_button.setEnabled(False)
        self.statusBar().showMessage("正在扫描缓存…")
        self.scan_thread = ScanThread(path)
        self.scan_thread.found.connect(self.show_urls)
        self.scan_thread.failed.connect(self.scan_failed)
        self.scan_thread.finished.connect(lambda: self.scan_button.setEnabled(True))
        self.scan_thread.start()

    def show_urls(self, urls: list[str]) -> None:
        self.player.stop()
        self.urls = sorted(urls, reverse=True)
        was_blocked = self.table.blockSignals(True)
        try:
            self.table.clearSelection()
            self.table.setRowCount(0)
            self.table.setRowCount(len(self.urls))
            for row, url in enumerate(self.urls):
                date = DATE_PATTERN.search(urlsplit(url).path)
                date_text = "-" if date is None else "-".join(date.groups())
                for column, value in enumerate((date_text, safe_filename(url), url)):
                    item = QTableWidgetItem(value)
                    item.setToolTip(url)
                    self.table.setItem(row, column, item)
        finally:
            self.table.blockSignals(was_blocked)
        self.filter_rows()
        self.statusBar().showMessage(f"扫描完成：找到 {len(urls)} 条不重复的 WebM 链接")

    def scan_failed(self, error: str) -> None:
        self.statusBar().showMessage("扫描失败")
        QMessageBox.critical(self, "读取失败", error)

    def filter_rows(self) -> None:
        term = self.search_edit.text().strip().lower()
        visible = 0
        for row in range(self.table.rowCount()):
            matched = not term or any(
                term in self.table.item(row, col).text().lower() for col in range(3)
            )
            self.table.setRowHidden(row, not matched)
            visible += matched
        self.count_label.setText(f"{visible} / {len(self.urls)} 条链接" if term else f"{len(self.urls)} 条链接")
        if self.selected_url() is None:
            self.table.clearSelection()
            first_visible = next((row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)), None)
            if first_visible is not None:
                self.table.selectRow(first_visible)
            else:
                self.selection_changed()

    def selected_url(self) -> str | None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        if self.table.isRowHidden(row) or row >= len(self.urls):
            return None
        return self.urls[row]

    def set_selection_enabled(self, enabled: bool) -> None:
        for widget in (
            self.preview_button,
            self.pause_button,
            self.browser_button,
            self.copy_button,
            self.download_button,
        ):
            widget.setEnabled(enabled)

    def selection_changed(self) -> None:
        url = self.selected_url()
        self.set_selection_enabled(url is not None)
        if url:
            self.preview()
        else:
            self.player.stop()
            self.preview_label.setText("选择一条链接后自动预览")

    def preview(self) -> None:
        url = self.selected_url()
        if not url:
            return
        self.preview_label.setText("正在加载预览…")
        self.player.setSource(QUrl(url))
        self.player.play()

    def media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.preview_label.setText("正在预览 · " + safe_filename(self.player.source().toString()))

    def playback_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        self.preview_label.setText("预览失败：" + (message or "系统缺少相应媒体支持，可用浏览器打开或先下载。"))

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif not self.player.source().isEmpty():
            self.player.play()

    def open_browser(self) -> None:
        url = self.selected_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def copy_url(self) -> None:
        url = self.selected_url()
        if url:
            QApplication.clipboard().setText(url)
            self.statusBar().showMessage("链接已复制")

    def download(self) -> None:
        url = self.selected_url()
        if not url or (self.download_thread and self.download_thread.isRunning()):
            return
        default = str(Path.home() / "Downloads" / safe_filename(url))
        selected, _ = QFileDialog.getSaveFileName(self, "保存壁纸", default, "WebM 视频 (*.webm)")
        if not selected:
            return
        destination = Path(selected)
        if destination.exists() and QMessageBox.question(
            self, "确认覆盖", f"文件已存在，确定覆盖吗？\n{destination}"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("正在下载…")
        self.download_thread = DownloadThread(url, destination)
        self.download_thread.progress.connect(self.download_progress)
        self.download_thread.completed.connect(self.download_completed)
        self.download_thread.failed.connect(self.download_failed)
        self.download_thread.cancelled.connect(lambda: self.statusBar().showMessage("下载已取消"))
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()

    def download_progress(self, received: int, total: int) -> None:
        if total:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, received * 100 // total))
            self.statusBar().showMessage(f"正在下载：{received / 1048576:.1f} / {total / 1048576:.1f} MB")
        else:
            self.statusBar().showMessage(f"正在下载：{received / 1048576:.1f} MB")

    def download_completed(self, path: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.statusBar().showMessage(f"下载完成：{path}")
        QMessageBox.information(self, "下载完成", path)

    def download_failed(self, error: str) -> None:
        self.statusBar().showMessage("下载失败")
        QMessageBox.critical(self, "下载失败", error)

    def download_finished(self) -> None:
        self.cancel_button.setEnabled(False)
        self.download_button.setEnabled(self.selected_url() is not None)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    def cancel_download(self) -> None:
        if self.download_thread:
            self.download_thread.cancel()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("正在取消下载…")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.information(self, "下载中", "请等待下载完成，或先取消下载。")
            event.ignore()
            return
        self.player.stop()
        super().closeEvent(event)


def configure_windows_taskbar() -> None:
    """让任务栏将本程序识别为独立应用，而不是 Python 解释器。"""
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)


def show_startup_notice(parent: QWidget) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("免费开源声明")
    dialog.setMinimumWidth(390)
    layout = QVBoxLayout(dialog)
    notice = QLabel(
        "本软件完全免费且开源<br>"
        "如果你是付费获得，大概是被骗了<br><br>"
        f'项目地址：<a href="{PROJECT_URL}">{PROJECT_URL}</a>'
    )
    notice.setTextFormat(Qt.TextFormat.RichText)
    notice.setOpenExternalLinks(True)
    notice.setWordWrap(True)
    layout.addWidget(notice)
    acknowledge = QPushButton("知道了")
    acknowledge.clicked.connect(dialog.accept)
    layout.addWidget(acknowledge, alignment=Qt.AlignmentFlag.AlignRight)
    dialog.exec()


def main() -> int:
    configure_windows_taskbar()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if LOGO_PATH.is_file():
        app.setWindowIcon(QIcon(str(LOGO_PATH)))
    window = MainWindow()
    window.show()
    show_startup_notice(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
