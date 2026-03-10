# serial-debug-assistant
# Serial Debug Assistant

基于 Python 3.11、PySide6、pyserial 开发的桌面串口调试助手。

## 已实现功能

- 枚举系统串口列表
- 选择波特率，默认 `115200`
- 打开串口 / 关闭串口
- 发送文本
- 实时接收并显示串口数据
- 清空接收区
- 基本异常提示，避免程序直接崩溃

## 项目结构

```text
serial_debug_assistant/
├─ app/
│  ├─ services/
│  │  └─ serial_service.py
│  └─ ui/
│     └─ main_window.py
├─ main.py
└─ requirements.txt
```

## 运行方式

1. 创建并激活 Python 3.11 虚拟环境
2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 启动应用

```bash
python main.py
```

## 依赖

- PySide6
- pyserial
