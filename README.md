# 米游壁纸提取

从米哈游启动器的 `data_1` 二进制缓存中提取 WebM 链接，自动去重，并提供筛选、预览、浏览器打开、复制链接和下载功能。

## 运行

需要 Python 3.10 或更新版本。在项目目录执行：

```powershell
python -m pip install -r requirements.txt
python mihoyo_wallpaper.py
```

窗口和 Windows 任务栏图标使用与程序同目录的 `logo.ico`。
程序启动时会尝试读取当前 Windows 账户的 `%APPDATA%\miHoYo\HYP\1_1\fedata\Cache\Cache_Data\data_1`。也可以点击“浏览…”选择其他账户复制出来的 `data_1` 文件。

扫描后会自动选择并预览第一条链接；切换列表选中项时，也会自动加载预览。“预览”按钮可重新播放当前项。“复制下载链接”按钮可复制当前选中的 WebM 地址，也可按 Ctrl+C。预览依赖本机 Qt 媒体后端对 WebM 的支持；如果无法播放，可点击“浏览器打开”或下载后用本机播放器观看。下载写入临时 `.part` 文件，完成后才替换目标文件。

## Nuitka 打包（Windows）

先在目标架构的 Python 环境安装依赖：

```powershell
python -m pip install -r requirements.txt Nuitka
```

本机 x64 构建示例：

```powershell
.\build_nuitka.cmd x64 "D:\Python311\python.exe"
```

生成的无控制台单文件程序位于 `dist\x64\miyobg-x64.exe`，包含 `logo.ico` 和 Qt 多媒体插件。脚本会调用 `D:\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat -arch=x64`。若要构建原生 ARM64 版本，请在 Windows ARM64 设备上安装 ARM64 Python、PySide6 和 Nuitka，再运行 `build_nuitka.cmd arm64 <ARM64 Python 路径>`。Nuitka 需要目标架构的 Python，不能只切换 `VsDevCmd.bat` 的 `-arch` 参数来交叉打包。当前 PySide6 / Qt 6 没有官方 Windows x86（32 位）发行包，因此本项目无法以受支持的依赖组合打包 x86 版本。
