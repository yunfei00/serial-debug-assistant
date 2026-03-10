from __future__ import annotations

from typing import Optional

import serial
from PySide6.QtCore import QObject, QThread, Signal
from serial.tools import list_ports


class SerialReadThread(QThread):
    """后台读取串口数据，避免阻塞界面。"""

    data_received = Signal(bytes)
    error_occurred = Signal(str)

    def __init__(self, serial_port: serial.Serial) -> None:
        super().__init__()
        self._serial_port = serial_port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                if not self._serial_port.is_open:
                    break

                chunk = self._serial_port.read(self._serial_port.in_waiting or 1)
                if chunk:
                    self.data_received.emit(chunk)
            except serial.SerialException as exc:
                if self._running:
                    self.error_occurred.emit(f"串口读取失败：{exc}")
                break
            except Exception as exc:  # noqa: BLE001
                if self._running:
                    self.error_occurred.emit(f"读取数据时发生异常：{exc}")
                break

    def stop(self) -> None:
        self._running = False
        self.wait(1000)


class SerialService(QObject):
    """串口服务，负责串口操作与状态管理。"""

    data_received = Signal(bytes)
    error_occurred = Signal(str)
    connection_changed = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._serial_port: Optional[serial.Serial] = None
        self._read_thread: Optional[SerialReadThread] = None

    def list_ports(self) -> list[str]:
        """枚举系统串口列表。"""
        ports = list_ports.comports()
        return [port.device for port in ports]

    def is_open(self) -> bool:
        return bool(self._serial_port and self._serial_port.is_open)

    def open_port(self, port_name: str, baudrate: int) -> None:
        """打开串口并启动读取线程。"""
        if self.is_open():
            raise RuntimeError("串口已经处于打开状态")

        if not port_name:
            raise ValueError("请选择串口")

        try:
            serial_port = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                timeout=0.1,
                write_timeout=1,
            )
        except serial.SerialException as exc:
            raise RuntimeError(f"打开串口失败：{exc}") from exc

        self._serial_port = serial_port
        self._read_thread = SerialReadThread(serial_port)
        self._read_thread.data_received.connect(self.data_received.emit)
        self._read_thread.error_occurred.connect(self._handle_thread_error)
        self._read_thread.start()
        self.connection_changed.emit(True, f"已打开串口：{port_name}")

    def close_port(self) -> None:
        """关闭串口并停止后台线程。"""
        port_name = self._serial_port.port if self._serial_port else ""

        if self._read_thread is not None:
            self._read_thread.stop()
            self._read_thread = None

        if self._serial_port is not None:
            try:
                if self._serial_port.is_open:
                    self._serial_port.close()
            except serial.SerialException as exc:
                self._serial_port = None
                self.connection_changed.emit(False, "串口已关闭")
                raise RuntimeError(f"关闭串口失败：{exc}") from exc
            finally:
                self._serial_port = None

        message = f"已关闭串口：{port_name}" if port_name else "串口已关闭"
        self.connection_changed.emit(False, message)

    def send_bytes(self, data: bytes) -> None:
        """发送字节数据。"""
        if not self.is_open() or self._serial_port is None:
            raise RuntimeError("串口未打开")

        if not data:
            raise ValueError("发送内容不能为空")

        try:
            self._serial_port.write(data)
        except serial.SerialTimeoutException as exc:
            raise RuntimeError(f"发送超时：{exc}") from exc
        except serial.SerialException as exc:
            raise RuntimeError(f"发送失败：{exc}") from exc

    def send_text(self, text: str) -> None:
        """发送文本数据。"""
        self.send_bytes(text.encode("utf-8"))

    def dispose(self) -> None:
        """释放资源，供界面退出时调用。"""
        if self.is_open():
            try:
                self.close_port()
            except RuntimeError as exc:
                self.error_occurred.emit(str(exc))

    def _handle_thread_error(self, message: str) -> None:
        self.error_occurred.emit(message)
        if self.is_open():
            try:
                self.close_port()
            except RuntimeError as exc:
                self.error_occurred.emit(str(exc))
