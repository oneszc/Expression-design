# Expression Design

一个面向微信表情包制作的 Agent Skill。从主题探索角色和画风，或直接沿用已有形象，完成一套有统一风格的聊天表情。

## 使用

把本仓库作为 `expression-design` 文件夹安装到 Agent 的 skills 目录，保留 `references/` 和 `scripts/`。支持 skills CLI 的环境可运行：

```bash
npx skills add oneszc/Expression-design
```

示例：

> 帮我做一套“周一不想上班”的微信表情包。

> 沿用这张角色图做 8 张动态微信表情，性格懒洋洋，主要和朋友聊天用。

未说明静态或动态时，Skill 会先询问。只有主题时展示多个实际样张方向；主要形象已确定时跳过方向对比。过程中只问影响结果的核心问题。

## 交付

- 整套名称（已有名称沿用，否则提供候选）。
- 8～24 张静态或动态表情。
- 详情页横幅、表情封面图、聊天面板图标各 1 张。
- 文件清单、规格检查结果，以及实际预览。

图像与动画制作依赖 Agent 当前可用的生成、编辑或渲染工具；本仓库没有内置图像模型，不需要固定厂商密钥。缺少出图能力时只能完成方案，不能生成实际素材。动态路径需要真实动画制作能力。

## 规格检查

Python 3.10+，Pillow：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/validate_pack.py /path/to/project/delivery/manifest.json --report /path/to/project/validation.json
python3 -m unittest discover -s tests -v
```

动态表情可使用统一导出工具：

```bash
python3 scripts/export_animation.py /path/to/project/sources/sequence.json --output-dir /path/to/project/previews/export-01
```

工具支持帧序列与帧网格裁切，保留每帧时长，统一调色板并合并连续重复帧，导出 GIF、浅/深背景逐帧对照和检查报告。可指定静止区域，标出帧间变化；角色身份、比例和动作质量仍需视觉检查。清单格式与草样/最终动画标准见 [动态制作说明](references/animated.md)。

规格基线采用用户提供的微信素材概览截图，详见 [微信交付要求](references/wechat-delivery.md)。检查通过仅代表文件符合该基线，视觉表现、实际聊天效果与微信审核需另外核对。Skill 不自动向微信投稿。

当前版本：0.2.0。已完成三种动态方向草样测试，尚未完成真实静态／动态整套生成的端到端验收。
