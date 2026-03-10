# Serial Debug Assistant

基于 Python 3.11、PySide6、pyserial 开发的桌面串口调试助手。

## 已实现功能

- 枚举系统串口列表
- 选择波特率，默认 `115200`
- 打开串口 / 关闭串口
- 发送文本
- 支持 `HEX` 发送
- 实时接收并显示串口数据
- 支持 `HEX` 显示
- 支持接收区自动换行显示
- 支持定时发送，可设置发送间隔并开始/停止
- 支持本次运行期间的发送历史记录
- 支持保存接收日志到文件
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

## 使用说明

- 文本发送时，直接输入内容后点击“发送”
- 勾选“HEX 发送”后，发送内容请按 `01 02 0A` 这类格式输入
- 勾选“HEX 显示”后，接收区将按十六进制显示
- 勾选“自动换行”后，接收区会按窗口宽度换行
- 定时发送可设置毫秒间隔，然后点击“开始定时发送”
- “发送历史”会保留本次运行期间成功发送过的内容
- “保存接收日志”会把当前接收区内容保存为 `UTF-8` 文本文件

## 依赖

- PySide6
- pyserial
