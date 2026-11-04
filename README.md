# Expression Design

**一句话，开始制作一套有自己语气的微信表情。**

从主题探索角色与画风，或沿用你已有的形象，把日常口头禅、职场吐槽和朋友之间的梗，变成一套风格统一、表达各异的静态或动态表情。

角色、动作、配字、横幅、封面、聊天图标，一起规划与交付。

角色示例 · 小卷已老实

| 收到 | 我裂开了 | 溜了溜了 |
|:---:|:---:|:---:|
| ![慵懒地抬爪回应收到](assets/showcase/收到.gif) | ![瞪眼捂脸表达我裂开了](assets/showcase/我裂开了.gif) | ![起身跑两步再坐回的溜了溜了](assets/showcase/溜了溜了.gif) |

## 快速开始

在支持 skills CLI 的环境中安装：

```bash
npx skills add oneszc/Expression-design
```

然后向 Agent 说出你的想法：

> 帮我做一套“周一不想上班”的微信表情包。

> 沿用这张角色图，做 8 张搞笑动态表情，主要和朋友聊天用。

> 做一套“别急着学 AI”的表情，先搜最近流行的表达作参考。

也可以把完整仓库放入 Agent 的 skills 目录，文件夹命名为 `expression-design`，保留其中的参考文档与脚本。

## 从一个梗，发展成一整套

### 没有角色？先看三个方向

给一个主题，就从轮廓、比例、神态和画风探索不同方向。通过评审的实际样张供你比较，选定喜欢的，再扩展整套；动态样张展示真实短循环。

### 已有形象？延续它的特点

提供角色图，保留它的辨识特征、线条、配色和气质，围绕不同聊天场景设计动作与配字。确认过的形象继续沿用，新增表情不用反复选角。

### 让每张表情都有自己的语气

同一句“收到”，可以认真、敷衍，也可以礼貌中带点疲惫。先想清楚表情在什么对话里使用，再设计神态、动作和节拍，让一套表情有共同性格，也有不同表达。

| 礼貌还在：好的呢 | 电量不足：不想动 |
|:---:|:---:|
| ![小卷微笑合爪回应好的呢](assets/showcase/好的呢.gif) | ![小卷无力地闭眼再睁开表达不想动](assets/showcase/不想动.gif) |

### 想找灵感？可以联网参考

需要时搜索表情案例，提炼画风、聊天语气和动作规律，再用于本套创作。参考附来源，热度有依据，不直接照搬现成角色。

## 选择简单，表达自由

| 选择 | 支持内容 |
|---|---|
| 制作模式 | 静态或动态 |
| 表情风格 | 搞笑、软萌可爱、丧/佛系、简笔画、像素、复古等，建议组合 1～2 项 |
| 表情主题 | 日常通用、工作/职场、考试/学习、情侣、游戏，以及你自己的梗 |

风格和主题都有“其它，自行输入”。已经说清楚的要求直接沿用，只补问缺少的信息；支持的宿主中使用原生选择卡片或弹窗，其它环境可直接文字回复。完整选项见 [风格与主题选择](references/preferences.md)。

## 先评审，再交付

制作结果交给独立子 Agent，从角色与风格、表达匹配、制作质量、聊天尺寸可用性四个维度评审。

**单项总分超过 80 分、表达分至少 18/25，且没有关键缺陷、必要检查完整，才作为合格结果主动展示。** 整套还会横向检查画风、动作和语义是否协调、有区别。

发现问题后针对具体项返修，默认最多 2 轮，再重新评审。动态重点检查表演、位置稳定、恢复和循环；封面与聊天图标则按实际尺寸检查辨识度与边缘。

交付前由脚本核对素材规格、评审记录和当前文件版本，检查通过再打包。评分辅助筛选，最终的角色方向和喜好由你决定。流程详见 [独立评审与返修](references/review.md)。

## 一套交付包含什么

| 内容 | 数量与规格 |
|---|---|
| 表情名称与介绍 | 名称不超过 8 字、无标点；介绍不超过 80 字 |
| 表情主图 | 默认 8 张，可指定 8～24 张；240×240，静态图或动态 GIF |
| 详情页横幅 | 1 张，750×400，无字情境画面 |
| 专辑封面 | 1 张，240×240，透明背景的正面半身或全身形象 |
| 聊天页图标 | 1 张，50×50，简洁清晰的透明正面头部 |
| 素材包 | 按聊天含义命名的独立文件、清单与经过检查的 ZIP |

文件可以直接看懂：`收到.gif`、`咖啡续命.gif`、`溜了溜了.gif`，不用逐个打开猜编号。配套图分别构图，按各自在微信中的展示用途处理背景、文字与留白。完整要求见 [微信素材规范](references/wechat-delivery.md)。

## 在你的 Agent 中使用

需要支持 Skill、图像生成或编辑、独立子 Agent 的环境。动态制作还需要连续动作制作、导出，以及能观察实际播放的工具。图像模型由 Agent 当前可用能力提供，可按自己的工具环境选择制作路线。

随附导出与检查脚本需要 Python 3.10+ 和 Pillow。FFmpeg、Node 等按需使用；开始前检查依赖，缺失时提供用途、安装提示和替代方案。详见 [环境与工具选择](references/environment.md)。

项目默认保存在工作区的 `output/expression-design/项目名/`。源图、过程素材与评审记录留在本地，ZIP只包含交付清单和最终素材，不自动提交GitHub或上传微信。

## 文档与工具

| 想了解 | 查看 |
|---|---|
| 完整制作流程 | [Skill 入口](SKILL.md) |
| 静态表情制作 | [静态制作参考](references/static.md) |
| 动作、节拍与循环 | [动态制作参考](references/animated.md) |
| 如何借鉴热门表情 | [联网参考](references/research.md) |
| 评分与返修 | [独立评审](references/review.md) |
| 评审文件与交付打包 | [报告格式与打包工具](references/review-report.md) |

<details>
<summary>开发者：导出、检查与测试</summary>

在仓库根目录使用 Python 3.10+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 从帧序列导出 GIF
.venv/bin/python scripts/export_animation.py /path/to/project/sources/sequence.json --output-dir /path/to/project/previews/export-01

# 检查整套文件规格
.venv/bin/python scripts/validate_pack.py /path/to/project/delivery/manifest.json --report /path/to/project/validation.json

# 核对最终评审并打包
.venv/bin/python scripts/package_reviewed.py /path/to/project/delivery/manifest.json /path/to/project/reviews/round-1/final.json --output /path/to/project/stickers-approved.zip

# 运行测试
.venv/bin/python -m unittest discover -s tests -v
```

导出目录、报告及 ZIP 使用新路径，保留已有版本。清单与评审格式见对应参考文档。

</details>

---

Expression Design · v0.2.8
