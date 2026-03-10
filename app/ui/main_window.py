from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
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
        self._setup_ui()
        self._bind_signals()
        self.refresh_ports()
        self._update_ui_state(False)

    def _setup_ui(self) -> None:
        self.setWindowTitle("串口调试助手")
        self.resize(820, 560)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)

        top_layout.addWidget(QLabel("串口："))
        self.port_combo = QComboBox()
        top_layout.addWidget(self.port_combo, 2)

        self.refresh_button = QPushButton("刷新")
        top_layout.addWidget(self.refresh_button)

        top_layout.addWidget(QLabel("波特率："))
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(self.BAUDRATES)
        self.baudrate_combo.setCurrentText("115200")
        top_layout.addWidget(self.baudrate_combo)

        self.open_button = QPushButton("打开串口")
        top_layout.addWidget(self.open_button)

        self.close_button = QPushButton("关闭串口")
        top_layout.addWidget(self.close_button)

        send_layout = QHBoxLayout()
        main_layout.addLayout(send_layout)

        send_layout.addWidget(QLabel("发送："))
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("请输入要发送的文本")
        send_layout.addWidget(self.send_input, 1)

        self.send_button = QPushButton("发送")
        send_layout.addWidget(self.send_button)

        self.receive_text = QTextEdit()
        self.receive_text.setReadOnly(True)
        self.receive_text.setPlaceholderText("接收数据显示区")
        main_layout.addWidget(self.receive_text, 1)

        bottom_layout = QHBoxLayout()
        main_layout.addLayout(bottom_layout)

        self.clear_button = QPushButton("清空接收区")
        bottom_layout.addWidget(self.clear_button)
        bottom_layout.addStretch()

        self.statusBar().showMessage("就绪")

    def _bind_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.open_button.clicked.connect(self.open_port)
        self.close_button.clicked.connect(self.close_port)
        self.send_button.clicked.connect(self.send_text)
        self.clear_button.clicked.connect(self.receive_text.clear)
        self.send_input.returnPressed.connect(self.send_text)

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
        text = self.send_input.text()

        try:
            self.serial_service.send_text(text)
        except (RuntimeError, ValueError) as exc:
            self.show_error(str(exc))
            return

        self.send_input.clear()
        self.statusBar().showMessage("发送成功")

    def append_received_text(self, text: str) -> None:
        self.receive_text.moveCursor(QTextCursor.MoveOperation.End)
        self.receive_text.insertPlainText(text)
        self.receive_text.moveCursor(QTextCursor.MoveOperation.End)

    def on_connection_changed(self, is_open: bool, message: str) -> None:
        self._update_ui_state(is_open)
        self.statusBar().showMessage(message)

    def _update_ui_state(self, is_open: bool) -> None:
        self.open_button.setEnabled(not is_open)
        self.close_button.setEnabled(is_open)
        self.send_button.setEnabled(is_open)
        self.send_input.setEnabled(is_open)
        self.port_combo.setEnabled(not is_open)
        self.baudrate_combo.setEnabled(not is_open)

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "提示", message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.serial_service.dispose()
        super().closeEvent(event)
