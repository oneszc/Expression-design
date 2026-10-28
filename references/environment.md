# 环境与工具选择

开始制作前使用本轮实际工具清单与只读探测，区分“已验证可用、缺少、未验证”。不要只根据某个 Skill 已安装就宣称其模型、账户、渲染器或浏览器可用。项目中在 `project.md` 记录选定路线、实际解释器/工具、版本与尚缺能力；只探测本次需要的依赖。

## 按任务选择能力

| 环节 | 需要的能力 | 缺失时的处理 |
|---|---|---|
| 角色与静态素材 | 可用的生图、绘制或图像编辑能力 | 若无可用替代，交付规划并标为尚未生成 |
| 动态制作 | 能实际生成连续动作或渲染逐帧的工具 | 先验证一张短循环；仅有静态生图不代表动画路线已成立 |
| 精确导出与随附校验 | Python 3.10+、Pillow；或先用已有图像工具导出，再补齐随附校验依赖 | 提供环境安装提示；未运行校验时明确记录 |
| GIF 编码 | 随附 `export_animation.py` 使用 Python + Pillow | 不要求 FFmpeg、Node 或付费模型 |
| 视频转帧或视频预览转换 | 可选 FFmpeg，或同等可用的视频工具 | 只有该路线需要时才提示安装；已有独立帧可直接走 Pillow 路线 |
| 关键姿态与动画过渡 | 按动作与画风选逐帧、可变形分层或混合工具，先验证姿态、接触和原速表演 | SVG、浏览器时间线、HyperFrames 等只是候选；能编码或插值不代表能完成所需形变，不以可用的刚性变换降低动作要求；选中后再核对依赖并加载相应说明 |
| 播放与视觉检查 | Agent 能观察的最终文件播放/逐帧查看能力 | 外部播放器能打开不等于 Agent 已观察；不可观察时提供实际 GIF 并标记播放待验收 |

优先复用已有能力与最少依赖。不默认绑定 image_gen、FFmpeg、浏览器、特定操作系统或模型厂商。额外账户、密钥或付费工具仅在确实需要且用户选定该路线时配置，不索要明文密钥。

## Python 与 Pillow

先使用候选解释器执行下列检查，版本不满足时检查环境中已有的其他解释器，后续所有命令使用同一个已验证解释器。默认 `python3` 不是版本保证。

```bash
python3 -c 'import sys; print(sys.version); sys.exit(0 if sys.version_info >= (3, 10) else 1)'
python3 -c 'import PIL; print(PIL.__version__)'
```

缺 Pillow 时，提示“随附 GIF 导出和文件规格检查需要 Pillow；当前解释器无法导入。建议在项目虚拟环境安装，已有授权则执行，否则先确认安装”。不要往全局 Python 强装。以已验证的 Python 3.10+ 创建环境，以下路径按实际项目和 Skill 安装位置替换：

```bash
python3 -m venv /path/to/project/.venv
/path/to/project/.venv/bin/python -m pip install -r /path/to/expression-design/requirements.txt
/path/to/project/.venv/bin/python -c 'import sys, PIL; print(sys.version); print(PIL.__version__)'
```

若 Python 本身缺失，按用户操作系统和已有包管理器提供安装办法。例如 macOS 已有 Homebrew 时可安装 `python`；没有 Homebrew 时提供 Python 官方安装方式，不顺带安装整个包管理器。安装后重新发现解释器，不假定安装目录。Windows 虚拟环境解释器在 `Scripts/python.exe`，不照搬 POSIX 路径。

## 可选 FFmpeg：检查、提示、复检

选定步骤确实需要 FFmpeg 时，先运行 `ffmpeg -version`；失败后区分未安装、PATH 不可见及工具无法执行，不直接假定缺安装。成功则使用现有版本。

缺失提示应具体，例如：“视频转独立帧这一步需要 FFmpeg，当前环境找不到。macOS 若已有 Homebrew，可执行 `brew install ffmpeg`；安装后用 `ffmpeg -version` 验证。若保留现有独立 PNG 帧，随附 Pillow 导出器无需 FFmpeg，可以继续这条路线。”

执行安装须沿用已有授权和工具权限；没有授权时先提示用途、安装位置/方式，再取得安装授权。无包管理器、无网络或无安装权限时，给出对应系统的手动安装入口或已验证的替代路线，继续不依赖该工具的规划工作，不循环重试或宣称安装成功。Node、动画渲染器等其他可选依赖同样按“选定路线 → 探测 → 缺失提示/替代 → 授权安装 → 实际复检”处理。

不要通过给静态图加扩展名、只做整图抖动或跳过校验，掩盖缺少动画、编辑或验证能力。
