from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.serial_service import SerialService


class MainWindow(QMainWindow):
    """主窗口。"""

    BAUDRATES = ["9600", "19200", "38400", "57600", "115200"]

    def __init__(self) -> None:
        super().__init__()
        self.serial_service = SerialService()
        self.auto_send_timer = QTimer(self)
        self._received_buffer = bytearray()
        self._send_history: list[str] = []

        self._setup_ui()
        self._bind_signals()
        self.refresh_ports()
        self._refresh_history_combo()
        self._update_ui_state(False)
        self._apply_wrap_mode(self.wrap_checkbox.isChecked())

    def _setup_ui(self) -> None:
        self.setWindowTitle("串口调试助手")
        self.resize(900, 620)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        connection_layout = QHBoxLayout()
        main_layout.addLayout(connection_layout)

        connection_layout.addWidget(QLabel("串口："))
        self.port_combo = QComboBox()
        connection_layout.addWidget(self.port_combo, 2)

        self.refresh_button = QPushButton("刷新")
        connection_layout.addWidget(self.refresh_button)

        connection_layout.addWidget(QLabel("波特率："))
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(self.BAUDRATES)
        self.baudrate_combo.setCurrentText("115200")
        connection_layout.addWidget(self.baudrate_combo)

        self.open_button = QPushButton("打开串口")
        connection_layout.addWidget(self.open_button)

        self.close_button = QPushButton("关闭串口")
        connection_layout.addWidget(self.close_button)

        send_layout = QHBoxLayout()
        main_layout.addLayout(send_layout)

        send_layout.addWidget(QLabel("发送："))
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("请输入要发送的文本，HEX 模式示例：01 02 0A")
        send_layout.addWidget(self.send_input, 1)

        self.send_button = QPushButton("发送")
        send_layout.addWidget(self.send_button)

        send_option_layout = QHBoxLayout()
        main_layout.addLayout(send_option_layout)

        self.hex_send_checkbox = QCheckBox("HEX 发送")
        send_option_layout.addWidget(self.hex_send_checkbox)

        send_option_layout.addWidget(QLabel("发送历史："))
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(260)
        send_option_layout.addWidget(self.history_combo, 1)
        send_option_layout.addStretch()

        timer_layout = QHBoxLayout()
        main_layout.addLayout(timer_layout)

        timer_layout.addWidget(QLabel("定时发送间隔(ms)："))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 3_600_000)
        self.interval_spin.setValue(1000)
        timer_layout.addWidget(self.interval_spin)

        self.start_timer_button = QPushButton("开始定时发送")
        timer_layout.addWidget(self.start_timer_button)

        self.stop_timer_button = QPushButton("停止定时发送")
        timer_layout.addWidget(self.stop_timer_button)
        timer_layout.addStretch()

        receive_control_layout = QHBoxLayout()
        main_layout.addLayout(receive_control_layout)

        self.hex_display_checkbox = QCheckBox("HEX 显示")
        receive_control_layout.addWidget(self.hex_display_checkbox)

        self.wrap_checkbox = QCheckBox("自动换行")
        self.wrap_checkbox.setChecked(True)
        receive_control_layout.addWidget(self.wrap_checkbox)

        receive_control_layout.addStretch()

        self.save_log_button = QPushButton("保存接收日志")
        receive_control_layout.addWidget(self.save_log_button)

        self.clear_button = QPushButton("清空接收区")
        receive_control_layout.addWidget(self.clear_button)

        self.receive_text = QTextEdit()
        self.receive_text.setReadOnly(True)
        self.receive_text.setPlaceholderText("接收数据显示区")
        main_layout.addWidget(self.receive_text, 1)

        self.statusBar().showMessage("就绪")

    def _bind_signals(self) -> None:
        self.refresh_button.clicked.connect(lambda: self.refresh_ports())
        self.open_button.clicked.connect(lambda: self.open_port())
        self.close_button.clicked.connect(lambda: self.close_port())
        self.send_button.clicked.connect(lambda: self.send_text())
        self.clear_button.clicked.connect(lambda: self.clear_receive_area())
        self.save_log_button.clicked.connect(lambda: self.save_receive_log())
        self.send_input.returnPressed.connect(self.send_text)

        self.history_combo.currentIndexChanged.connect(self.load_history_text)
        self.hex_display_checkbox.toggled.connect(lambda _checked: self._refresh_receive_display())
        self.wrap_checkbox.toggled.connect(self._apply_wrap_mode)
        self.start_timer_button.clicked.connect(lambda: self.start_auto_send())
        self.stop_timer_button.clicked.connect(lambda: self.stop_auto_send())

        self.auto_send_timer.timeout.connect(self.send_text_by_timer)

        self.serial_service.data_received.connect(self.append_received_text)
        self.serial_service.error_occurred.connect(self.show_error)
        self.serial_service.connection_changed.connect(self.on_connection_changed)

    def refresh_ports(self) -> None:
        current_port = self.port_combo.currentText()
        ports = self.serial_service.list_ports()

        self.port_combo.clear()
        self.port_combo.addItems(ports)

        if current_port and current_port in ports:
            self.port_combo.setCurrentText(current_port)

        message = f"已刷新，共发现 {len(ports)} 个串口" if ports else "未发现可用串口"
        self.statusBar().showMessage(message)

    def open_port(self) -> None:
        port_name = self.port_combo.currentText().strip()
        baudrate = int(self.baudrate_combo.currentText())

        try:
            self.serial_service.open_port(port_name, baudrate)
        except (RuntimeError, ValueError) as exc:
            self.show_error(str(exc))

    def close_port(self) -> None:
        try:
            self.serial_service.close_port()
        except RuntimeError as exc:
            self.show_error(str(exc))

    def send_text(self) -> None:
        self._send_current_text(clear_input=True, show_success=True)

    def send_text_by_timer(self) -> None:
        if not self._send_current_text(clear_input=False, show_success=False):
            self.stop_auto_send(show_message=False)

    def _send_current_text(self, clear_input: bool, show_success: bool) -> bool:
        text = self.send_input.text()

        try:
            data = self._build_send_data(text)
            self.serial_service.send_bytes(data)
        except (RuntimeError, ValueError) as exc:
            self.show_error(str(exc))
            return False

        self._record_send_history(text)

        if clear_input:
            self.send_input.clear()

        if show_success:
            self.statusBar().showMessage("发送成功")

        return True

    def _build_send_data(self, text: str) -> bytes:
        if text == "":
            raise ValueError("发送内容不能为空")

        if self.hex_send_checkbox.isChecked():
            try:
                data = bytes.fromhex(text)
            except ValueError as exc:
                raise ValueError("HEX 发送格式不正确，请使用如 01 02 0A 的格式") from exc
        else:
            data = text.encode("utf-8")

        if not data:
            raise ValueError("发送内容不能为空")

        return data

    def append_received_text(self, data: bytes) -> None:
        self._received_buffer.extend(data)
        self._refresh_receive_display()

    def _refresh_receive_display(self) -> None:
        if not self._received_buffer:
            self.receive_text.clear()
            return

        raw_data = bytes(self._received_buffer)
        if self.hex_display_checkbox.isChecked():
            text = raw_data.hex(" ").upper()
        else:
            text = raw_data.decode("utf-8", errors="replace")

        self.receive_text.setPlainText(text)
        self.receive_text.moveCursor(QTextCursor.MoveOperation.End)

    def _apply_wrap_mode(self, checked: bool) -> None:
        mode = QTextEdit.LineWrapMode.WidgetWidth if checked else QTextEdit.LineWrapMode.NoWrap
        self.receive_text.setLineWrapMode(mode)

    def clear_receive_area(self) -> None:
        self._received_buffer.clear()
        self.receive_text.clear()
        self.statusBar().showMessage("接收区已清空")

    def save_receive_log(self) -> None:
        if not self._received_buffer:
            self.show_error("当前没有可保存的接收日志")
            return

        default_name = f"serial_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存接收日志",
            default_name,
            "文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(self.receive_text.toPlainText())
        except OSError as exc:
            self.show_error(f"保存日志失败：{exc}")
            return

        self.statusBar().showMessage(f"日志已保存到：{file_path}")

    def start_auto_send(self) -> None:
        if self.auto_send_timer.isActive():
            return

        if not self.serial_service.is_open():
            self.show_error("请先打开串口，再启动定时发送")
            return

        try:
            self._build_send_data(self.send_input.text())
        except ValueError as exc:
            self.show_error(str(exc))
            return

        self.auto_send_timer.start(self.interval_spin.value())
        self._update_ui_state(True)
        self.statusBar().showMessage("已启动定时发送")

    def stop_auto_send(self, show_message: bool = True) -> None:
        if self.auto_send_timer.isActive():
            self.auto_send_timer.stop()

        self._update_ui_state(self.serial_service.is_open())
        if show_message:
            self.statusBar().showMessage("已停止定时发送")

    def _record_send_history(self, text: str) -> None:
        if self._send_history and self._send_history[0] == text:
            return

        if text in self._send_history:
            self._send_history.remove(text)

        self._send_history.insert(0, text)
        self._send_history = self._send_history[:30]
        self._refresh_history_combo()

    def _refresh_history_combo(self) -> None:
        self.history_combo.blockSignals(True)
        self.history_combo.clear()

        if self._send_history:
            self.history_combo.addItems(self._send_history)
            self.history_combo.setEnabled(not self.auto_send_timer.isActive())
        else:
            self.history_combo.addItem("暂无历史")
            self.history_combo.setEnabled(False)

        self.history_combo.blockSignals(False)

    def load_history_text(self, index: int) -> None:
        if not self._send_history or index < 0 or index >= len(self._send_history):
            return

        self.send_input.setText(self._send_history[index])

    def on_connection_changed(self, is_open: bool, message: str) -> None:
        if not is_open:
            self.stop_auto_send(show_message=False)
        self._update_ui_state(is_open)
        self.statusBar().showMessage(message)

    def _update_ui_state(self, is_open: bool) -> None:
        is_auto_sending = self.auto_send_timer.isActive()

        self.open_button.setEnabled(not is_open)
        self.close_button.setEnabled(is_open)
        self.refresh_button.setEnabled(not is_open)
        self.send_button.setEnabled(is_open and not is_auto_sending)
        self.send_input.setEnabled(is_open and not is_auto_sending)
        self.hex_send_checkbox.setEnabled(is_open and not is_auto_sending)
        self.start_timer_button.setEnabled(is_open and not is_auto_sending)
        self.stop_timer_button.setEnabled(is_auto_sending)
        self.interval_spin.setEnabled(is_open and not is_auto_sending)
        self.port_combo.setEnabled(not is_open)
        self.baudrate_combo.setEnabled(not is_open)

        if self._send_history:
            self.history_combo.setEnabled(not is_auto_sending)
        else:
            self.history_combo.setEnabled(False)

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "提示", message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop_auto_send(show_message=False)
        self.serial_service.dispose()
        super().closeEvent(event)
