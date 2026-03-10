from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SerialPortInfo:
    """串口基础信息。"""

    device: str
    description: str = ""
    manufacturer: str = ""
    hwid: str = ""

    @property
    def display_name(self) -> str:
        if self.description and self.description != "n/a":
            return f"{self.device} - {self.description}"
        return self.device


@dataclass(slots=True)
class SerialConfig:
    """串口连接配置。"""

    port_name: str
    baudrate: int
    data_bits: int = 8
    parity: str = "N"
    stop_bits: float = 1.0
    timeout: float = 0.1
    write_timeout: float = 1.0
