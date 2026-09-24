# 米游壁纸提取

从米哈游启动器的 `data_1` 二进制缓存中提取 WebM 链接，自动去重，并提供筛选、预览、浏览器打开、复制链接和下载功能。

## 运行

需要 Python 3.10 或更新版本。在项目目录执行：

```powershell
python -m pip install -r requirements.txt
python mihoyo_wallpaper.py
```

窗口和 Windows 任务栏图标使用与程序同目录的 `logo.ico`。
程序每次启动时会显示免费开源提示，并提供可点击的[项目地址](https://github.com/lrgx/miyobg.git)。

程序启动时会尝试读取当前 Windows 账户的 `%APPDATA%\miHoYo\HYP\1\_1\fedata\Cache\Cache\_Data\data_1`。也可以点击“浏览…”选择其他账户复制出来的 `data_1` 文件。

扫描后会自动选择并预览第一条链接；切换列表选中项时，也会自动加载预览。“预览”按钮可重新播放当前项。“复制下载链接”按钮可复制当前选中的 WebM 地址，也可按 Ctrl+C。预览依赖本机 Qt 媒体后端对 WebM 的支持；如果无法播放，可点击“浏览器打开”或下载后用本机播放器观看。下载写入临时 `.part` 文件，完成后才替换目标文件。
