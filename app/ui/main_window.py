from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSettings, QTimer
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

from app.core.models import SerialConfig, SerialPortInfo
from app.services.serial_service import SerialService


class MainWindow(QMainWindow):
    """主窗口。"""

    DIR_SEND = "send"
    DIR_RECEIVE = "receive"

    BAUDRATES = ["9600", "19200", "38400", "57600", "115200"]
    DATA_BITS = ["5", "6", "7", "8"]
    PARITY_OPTIONS = [("无校验", "N"), ("奇校验", "O"), ("偶校验", "E")]
    STOP_BITS_OPTIONS = [("1", "1.0"), ("1.5", "1.5"), ("2", "2.0")]
    LINE_ENDING_OPTIONS = [
        ("无", ""),
        ("CR(\\r)", "\r"),
        ("LF(\\n)", "\n"),
        ("CRLF(\\r\\n)", "\r\n"),
    ]
    SETTINGS_ORG = "serial-debug-assistant"
    SETTINGS_APP = "main-window"
    SETTINGS_LAST_SEND = "send/last_command"

    def __init__(self) -> None:
        super().__init__()
        self.serial_service = SerialService()
        self.settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
        self.auto_send_timer = QTimer(self)
        self._available_ports: list[SerialPortInfo] = []
        self._received_buffer = bytearray()
        self._log_entries: list[tuple[str, str, bytes, bool]] = []
        self._send_history: list[str] = []
        self._send_byte_count = 0
        self._receive_byte_count = 0
        self._pending_send_bytes = 0

        self._setup_ui()
        self._bind_signals()
        self.refresh_ports()
        self._refresh_history_combo()
        self._update_transfer_stats()
        self._update_ui_state(False)
        self._apply_wrap_mode(self.wrap_checkbox.isChecked())
        self._load_persistent_state()

    def _setup_ui(self) -> None:
        self.setWindowTitle("串口调试助手")
        self.resize(980, 680)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        connection_layout = QHBoxLayout()
        main_layout.addLayout(connection_layout)

        connection_layout.addWidget(QLabel("串口："))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(220)
        connection_layout.addWidget(self.port_combo, 2)

        self.refresh_button = QPushButton("刷新")
        connection_layout.addWidget(self.refresh_button)

        connection_layout.addWidget(QLabel("波特率："))
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(self.BAUDRATES)
        self.baudrate_combo.setCurrentText("115200")
        connection_layout.addWidget(self.baudrate_combo)

        connection_layout.addWidget(QLabel("数据位："))
        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(self.DATA_BITS)
        self.data_bits_combo.setCurrentText("8")
        connection_layout.addWidget(self.data_bits_combo)

        connection_layout.addWidget(QLabel("校验位："))
        self.parity_combo = QComboBox()
        for label, value in self.PARITY_OPTIONS:
            self.parity_combo.addItem(label, value)
        connection_layout.addWidget(self.parity_combo)

        connection_layout.addWidget(QLabel("停止位："))
        self.stop_bits_combo = QComboBox()
        for label, value in self.STOP_BITS_OPTIONS:
            self.stop_bits_combo.addItem(label, value)
        connection_layout.addWidget(self.stop_bits_combo)

        self.open_button = QPushButton("打开串口")
        connection_layout.addWidget(self.open_button)

        self.close_button = QPushButton("关闭串口")
        connection_layout.addWidget(self.close_button)

        info_layout = QHBoxLayout()
        main_layout.addLayout(info_layout)

        info_layout.addWidget(QLabel("端口信息："))
        self.port_info_label = QLabel("未发现可用串口")
        self.port_info_label.setWordWrap(True)
        info_layout.addWidget(self.port_info_label, 1)

        self.stats_label = QLabel("send: 0 bytes  receive: 0 bytes")
        info_layout.addWidget(self.stats_label)

        self.reset_stats_button = QPushButton("清零统计")
        info_layout.addWidget(self.reset_stats_button)

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

        send_option_layout.addWidget(QLabel("行尾："))
        self.line_ending_combo = QComboBox()
        for label, value in self.LINE_ENDING_OPTIONS:
            self.line_ending_combo.addItem(label, value)
        self.line_ending_combo.setCurrentText("CRLF(\\r\\n)")
        send_option_layout.addWidget(self.line_ending_combo)

        self.at_button = QPushButton("发送 AT")
        send_option_layout.addWidget(self.at_button)

        send_option_layout.addWidget(QLabel("发送历史："))
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(280)
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
        self.at_button.clicked.connect(lambda: self.send_at_command())
        self.clear_button.clicked.connect(lambda: self.clear_receive_area())
        self.save_log_button.clicked.connect(lambda: self.save_receive_log())
        self.reset_stats_button.clicked.connect(lambda: self.reset_transfer_stats())
        self.send_input.returnPressed.connect(self.send_text)

        self.port_combo.currentIndexChanged.connect(self._on_port_changed)
        self.history_combo.currentIndexChanged.connect(self.load_history_text)
        self.hex_display_checkbox.toggled.connect(lambda _checked: self._refresh_receive_display())
        self.hex_send_checkbox.toggled.connect(self._on_hex_send_toggled)
        self.wrap_checkbox.toggled.connect(self._apply_wrap_mode)
        self.start_timer_button.clicked.connect(lambda: self.start_auto_send())
        self.stop_timer_button.clicked.connect(lambda: self.stop_auto_send())

        self.auto_send_timer.timeout.connect(self.send_text_by_timer)

        self.serial_service.data_received.connect(self.append_received_text)
        self.serial_service.data_sent.connect(self.on_data_sent)
        self.serial_service.error_occurred.connect(self.show_error)
        self.serial_service.connection_changed.connect(self.on_connection_changed)

    def refresh_ports(self) -> None:
        current_port = self._current_port_name()
        self._available_ports = self.serial_service.list_ports()

        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        for port_info in self._available_ports:
            self.port_combo.addItem(port_info.display_name, port_info.device)
        self.port_combo.blockSignals(False)

        if current_port:
            index = self.port_combo.findData(current_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

        self._update_port_info()
        count = len(self._available_ports)
        message = f"已刷新，共发现 {count} 个串口" if count else "未发现可用串口"
        self.statusBar().showMessage(message)

    def open_port(self) -> None:
        try:
            config = self._build_serial_config()
            self.serial_service.open_port(config)
            self.reset_transfer_stats(show_message=False)
        except (RuntimeError, ValueError) as exc:
            self.show_error(str(exc))

    def close_port(self) -> None:
        try:
            self.serial_service.close_port()
        except RuntimeError as exc:
            self.show_error(str(exc))

    def send_text(self) -> None:
        self._send_current_text(clear_input=False, show_success=True)

    def send_at_command(self) -> None:
        self.send_input.setText("AT")
        self._send_current_text(clear_input=False, show_success=True)

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

        self._send_byte_count += len(data)
        self._pending_send_bytes += len(data)
        self._update_transfer_stats()
        self._record_send_history(text)
        self.settings.setValue(self.SETTINGS_LAST_SEND, text)
        self._append_log_entry(self.DIR_SEND, data, is_hex=self.hex_send_checkbox.isChecked())

        if clear_input:
            self.send_input.clear()

        if show_success:
            self.statusBar().showMessage(f"发送请求已提交，等待串口发送 {len(data)} 字节")

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
            line_ending = str(self.line_ending_combo.currentData() or "")
            data = f"{text}{line_ending}".encode("utf-8")

        if not data:
            raise ValueError("发送内容不能为空")

        return data

    def append_received_text(self, data: bytes) -> None:
        self._received_buffer.extend(data)
        self._receive_byte_count += len(data)
        self._update_transfer_stats()
        self._append_log_entry(self.DIR_RECEIVE, data, is_hex=False)
        self._refresh_receive_display()

    def on_data_sent(self, sent_bytes: int) -> None:
        self._pending_send_bytes = max(0, self._pending_send_bytes - sent_bytes)
        self.statusBar().showMessage(
            f"串口已发送 {sent_bytes} 字节，待发送队列剩余 {self._pending_send_bytes} 字节"
        )

    def _refresh_receive_display(self) -> None:
        if not self._log_entries:
            self.receive_text.clear()
            return

        lines = []
        for timestamp, direction, data, is_hex in self._log_entries:
            use_hex = is_hex or (direction == self.DIR_RECEIVE and self.hex_display_checkbox.isChecked())
            payload = data.hex(" ").upper() if use_hex else data.decode("utf-8", errors="replace")
            lines.append(f"[{timestamp}] {direction}: {payload}")
        text = "\n".join(lines)

        self.receive_text.setPlainText(text)
        self.receive_text.moveCursor(QTextCursor.MoveOperation.End)

    def _apply_wrap_mode(self, checked: bool) -> None:
        mode = QTextEdit.LineWrapMode.WidgetWidth if checked else QTextEdit.LineWrapMode.NoWrap
        self.receive_text.setLineWrapMode(mode)

    def clear_receive_area(self) -> None:
        self._received_buffer.clear()
        self._log_entries.clear()
        self.receive_text.clear()
        self.statusBar().showMessage("接收区已清空")

    def save_receive_log(self) -> None:
        if not self._log_entries:
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

    def reset_transfer_stats(self, show_message: bool = True) -> None:
        self._send_byte_count = 0
        self._receive_byte_count = 0
        self._pending_send_bytes = 0
        self._update_transfer_stats()
        if show_message:
            self.statusBar().showMessage("收发统计已清零")

    def _update_transfer_stats(self) -> None:
        self.stats_label.setText(
            f"send: {self._send_byte_count} bytes  receive: {self._receive_byte_count} bytes"
        )

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

    def _append_log_entry(self, direction: str, data: bytes, is_hex: bool) -> None:
        processed_data = data
        if not is_hex:
            if direction == self.DIR_SEND:
                processed_data = data.rstrip(b"\r\n")
            elif direction == self.DIR_RECEIVE:
                processed_data = data.strip(b"\r\n")
                if not processed_data:
                    return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._log_entries.append((timestamp, direction, processed_data, is_hex))

    def _load_persistent_state(self) -> None:
        last_command = str(self.settings.value(self.SETTINGS_LAST_SEND, "") or "")
        if last_command:
            self.send_input.setText(last_command)

    def on_connection_changed(self, is_open: bool, message: str) -> None:
        if not is_open:
            self.stop_auto_send(show_message=False)
            self._pending_send_bytes = 0
        self._update_ui_state(is_open)
        self.statusBar().showMessage(message)

    def _update_ui_state(self, is_open: bool) -> None:
        is_auto_sending = self.auto_send_timer.isActive()

        self.open_button.setEnabled(not is_open)
        self.close_button.setEnabled(is_open)
        self.refresh_button.setEnabled(not is_open)
        self.port_combo.setEnabled(not is_open)
        self.baudrate_combo.setEnabled(not is_open)
        self.data_bits_combo.setEnabled(not is_open)
        self.parity_combo.setEnabled(not is_open)
        self.stop_bits_combo.setEnabled(not is_open)

        self.send_button.setEnabled(is_open and not is_auto_sending)
        self.send_input.setEnabled(is_open and not is_auto_sending)
        self.hex_send_checkbox.setEnabled(is_open and not is_auto_sending)
        self.line_ending_combo.setEnabled(is_open and not is_auto_sending and not self.hex_send_checkbox.isChecked())
        self.at_button.setEnabled(is_open and not is_auto_sending)
        self.start_timer_button.setEnabled(is_open and not is_auto_sending)
        self.stop_timer_button.setEnabled(is_auto_sending)
        self.interval_spin.setEnabled(is_open and not is_auto_sending)

        if self._send_history:
            self.history_combo.setEnabled(not is_auto_sending)
        else:
            self.history_combo.setEnabled(False)

    def _on_hex_send_toggled(self, _checked: bool) -> None:
        self._update_ui_state(self.serial_service.is_open())

    def _build_serial_config(self) -> SerialConfig:
        port_name = self._current_port_name()
        if not port_name:
            raise ValueError("请选择串口")

        return SerialConfig(
            port_name=port_name,
            baudrate=int(self.baudrate_combo.currentText()),
            data_bits=int(self.data_bits_combo.currentText()),
            parity=str(self.parity_combo.currentData()),
            stop_bits=float(self.stop_bits_combo.currentData()),
        )

    def _current_port_name(self) -> str:
        data = self.port_combo.currentData()
        return str(data) if data else ""

    def _on_port_changed(self, _index: int) -> None:
        self._update_port_info()

    def _update_port_info(self) -> None:
        port_info = self._get_selected_port_info()
        if port_info is None:
            self.port_info_label.setText("未发现可用串口")
            return

        details = [f"设备：{port_info.device}"]
        if port_info.description:
            details.append(f"描述：{port_info.description}")
        if port_info.manufacturer:
            details.append(f"厂商：{port_info.manufacturer}")
        if port_info.hwid:
            details.append(f"硬件ID：{port_info.hwid}")
        self.port_info_label.setText("  |  ".join(details))

    def _get_selected_port_info(self) -> SerialPortInfo | None:
        port_name = self._current_port_name()
        for port_info in self._available_ports:
            if port_info.device == port_name:
                return port_info
        return None

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "提示", message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop_auto_send(show_message=False)
        self.serial_service.dispose()
        super().closeEvent(event)
