# 抖音公开视频下载脚本

使用 Python 的 yt-dlp 库。最初通过命令行下载，这个脚本保存相同的下载设置。

## 本次环境直接运行

```sh
/tmp/bruce-finance-research/.venv/bin/python output/布鲁斯的金融宝藏/tools/download_videos.py
```

默认下载四条研究视频，也可以在脚本后传一个或多个公开视频 URL。`--output` 可指定保存目录。

## 重建独立环境

以下命令在本目录执行，每行单独运行：

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -c 'from pathlib import Path; import subprocess, yt_dlp; subprocess.run(["patch", "-p1", "-i", str(Path("yt-dlp-douyin-fix.diff").resolve())], cwd=Path(yt_dlp.__file__).parent.parent, check=True)'
.venv/bin/python download_videos.py
```

## 修复来源和限制

- yt-dlp 官方仓库：https://github.com/yt-dlp/yt-dlp
- 本次使用的抖音提取器修复：https://github.com/yt-dlp/yt-dlp/pull/17826
- 随附 diff 是本次实际下载并应用的快照。修改仅位于独立虚拟环境；普通未修复版本在本机返回 403 / Fresh cookies needed。
- 运行时未读取个人浏览器 Cookie，也未使用登录账号；提取器会建立匿名访客会话。
- 下载会同时保存 `.info.json` 元数据，并尝试保存平台提供的独立字幕。已成功下载的三条视频没有独立字幕，音频转写尚未完成。
- 本次三个成功的 ID：7689639585425056591、7700469388663999720、7692341302306897984。
- 黄金复盘 7690782528969594728 本次仍返回 Fresh cookies needed，不能保证所有链接都成功。
- 输出默认位于上一级 `videos/`，既有文件不覆盖。平台接口变化可能使脚本失效。
