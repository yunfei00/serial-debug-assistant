from __future__ import annotations

import queue
from typing import Optional

import serial
from PySide6.QtCore import QObject, QThread, Signal
from serial.tools import list_ports

from app.core.models import SerialConfig, SerialPortInfo


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

                waiting = self._serial_port.in_waiting
                read_size = waiting if waiting > 0 else 1
                chunk = self._serial_port.read(read_size)
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


class SerialWriteThread(QThread):
    """后台发送串口数据，避免发送阻塞界面。"""

    data_sent = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, serial_port: serial.Serial) -> None:
        super().__init__()
        self._serial_port = serial_port
        self._running = True
        self._send_queue: queue.Queue[bytes] = queue.Queue()

    def run(self) -> None:
        while self._running:
            try:
                data = self._send_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if data == b"" and not self._running:
                break

            try:
                if not self._serial_port.is_open:
                    break
                sent = self._write_all(data)
                self._serial_port.flush()
                self.data_sent.emit(sent)
            except serial.SerialTimeoutException as exc:
                if self._running:
                    self.error_occurred.emit(f"发送超时：{exc}")
                break
            except serial.SerialException as exc:
                if self._running:
                    self.error_occurred.emit(f"发送失败：{exc}")
                break
            except Exception as exc:  # noqa: BLE001
                if self._running:
                    self.error_occurred.emit(f"发送数据时发生异常：{exc}")
                break

    def enqueue(self, data: bytes) -> None:
        self._send_queue.put(data)

    def _write_all(self, data: bytes) -> int:
        """确保一次任务中的字节全部发送完成。"""
        view = memoryview(data)
        total_sent = 0

        while total_sent < len(view):
            sent = self._serial_port.write(view[total_sent:])
            if sent <= 0:
                raise serial.SerialTimeoutException("写入串口返回 0 字节")
            total_sent += sent

        return total_sent

    def stop(self) -> None:
        self._running = False
        self._send_queue.put(b"")
        self.wait(1000)


class SerialService(QObject):
    """串口服务，负责串口操作与状态管理。"""

    data_received = Signal(bytes)
    data_sent = Signal(int)
    error_occurred = Signal(str)
    connection_changed = Signal(bool, str)

    BYTE_SIZE_MAP = {
        5: serial.FIVEBITS,
        6: serial.SIXBITS,
        7: serial.SEVENBITS,
        8: serial.EIGHTBITS,
    }
    PARITY_MAP = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
    }
    STOP_BITS_MAP = {
        1.0: serial.STOPBITS_ONE,
        1.5: serial.STOPBITS_ONE_POINT_FIVE,
        2.0: serial.STOPBITS_TWO,
    }

    def __init__(self) -> None:
        super().__init__()
        self._serial_port: Optional[serial.Serial] = None
        self._read_thread: Optional[SerialReadThread] = None
        self._write_thread: Optional[SerialWriteThread] = None

    def list_ports(self) -> list[SerialPortInfo]:
        """枚举系统串口列表。"""
        ports = list_ports.comports()
        return [
            SerialPortInfo(
                device=port.device,
                description=port.description or "",
                manufacturer=port.manufacturer or "",
                hwid=port.hwid or "",
            )
            for port in ports
        ]

    def is_open(self) -> bool:
        return bool(self._serial_port and self._serial_port.is_open)

    def open_port(self, config_or_port_name: SerialConfig | str, baudrate: int | None = None) -> None:
        """打开串口并启动读取线程。"""
        if self.is_open():
            raise RuntimeError("串口已经处于打开状态")

        config = self._normalize_config(config_or_port_name, baudrate)

        try:
            serial_port = serial.Serial(
                port=config.port_name,
                baudrate=config.baudrate,
                bytesize=self._get_bytesize(config.data_bits),
                parity=self._get_parity(config.parity),
                stopbits=self._get_stopbits(config.stop_bits),
                timeout=config.timeout,
                write_timeout=config.write_timeout,
            )
            serial_port.reset_output_buffer()
        except serial.SerialException as exc:
            raise RuntimeError(f"打开串口失败：{exc}") from exc

        self._serial_port = serial_port

        self._read_thread = SerialReadThread(serial_port)
        self._read_thread.data_received.connect(self.data_received.emit)
        self._read_thread.error_occurred.connect(self._handle_thread_error)
        self._read_thread.start()

        self._write_thread = SerialWriteThread(serial_port)
        self._write_thread.data_sent.connect(self.data_sent.emit)
        self._write_thread.error_occurred.connect(self._handle_thread_error)
        self._write_thread.start()

        self.connection_changed.emit(
            True,
            f"已打开串口：{config.port_name}，{config.baudrate} bps，{config.data_bits}{config.parity}{self._format_stop_bits(config.stop_bits)}",
        )

    def close_port(self) -> None:
        """关闭串口并停止后台线程。"""
        port_name = self._serial_port.port if self._serial_port else ""

        if self._read_thread is not None:
            self._read_thread.stop()
            self._read_thread = None

        if self._write_thread is not None:
            self._write_thread.stop()
            self._write_thread = None

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
        if not self.is_open() or self._serial_port is None or self._write_thread is None:
            raise RuntimeError("串口未打开")

        if not data:
            raise ValueError("发送内容不能为空")

        self._write_thread.enqueue(data)

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

    def _normalize_config(self, config_or_port_name: SerialConfig | str, baudrate: int | None) -> SerialConfig:
        if isinstance(config_or_port_name, SerialConfig):
            config = config_or_port_name
        else:
            if not config_or_port_name:
                raise ValueError("请选择串口")
            if baudrate is None:
                raise ValueError("缺少波特率配置")
            config = SerialConfig(port_name=config_or_port_name, baudrate=baudrate)

        if not config.port_name:
            raise ValueError("请选择串口")

        return config

    def _get_bytesize(self, data_bits: int) -> int:
        try:
            return self.BYTE_SIZE_MAP[data_bits]
        except KeyError as exc:
            raise ValueError(f"不支持的数据位：{data_bits}") from exc

    def _get_parity(self, parity: str) -> str:
        try:
            return self.PARITY_MAP[parity]
        except KeyError as exc:
            raise ValueError(f"不支持的校验位：{parity}") from exc

    def _get_stopbits(self, stop_bits: float) -> float:
        try:
            return self.STOP_BITS_MAP[stop_bits]
        except KeyError as exc:
            raise ValueError(f"不支持的停止位：{stop_bits}") from exc

    def _format_stop_bits(self, stop_bits: float) -> str:
        stop_bits_value = float(stop_bits)
        if stop_bits_value.is_integer():
            return str(int(stop_bits_value))
        return str(stop_bits_value)
