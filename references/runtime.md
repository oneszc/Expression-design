# 执行预算、断点与收尾

本流程不依赖某个宿主的后台任务机制。随附工具保存状态与报告；调用、监控和中止子 Agent 仍由主 Agent 使用实际宿主工具执行。没有取消能力时停止新任务、记录仍在运行的任务并告知用户，不能宣称已经强制终止。

## 开始前做小样闭环

先确定独立评审是否能读取本地文件、查看全部解码帧和浅/深底，以及是否能真正观察连续播放。用一个代表动作验证选定的生成路线、导出、评审落盘和验收方式，再扩成整套。动画生成耗时也计入预算，不为通过测试先造一整套。

小样只验证单项链路，不把一个文件当作满足微信数量要求的正式ZIP。可以先写含全部计划路径的manifest，用 `review_records.py --check-only` 检查已生成的小样片段；未生成的文件不伪报通过。首次使用工具时运行 `--help` 核对调用方式。正式打包仍须完整真实素材通过。

无法观察播放时，在扩套前说明需用户人工播放验收，并取得用户对这条路线的接受；不靠重复换评审 Agent 解决能力缺失。无子 Agent 时仍沿用环境参考的人工替代边界，不伪造独立评分。工具或生成路线失败后，最多尝试一次有明确依据的替代，仍失败则保存进度并报告，不从零开发大型绘制引擎来掩盖缺能力。

## 项目预算

主 Agent 是 state.json 的唯一写入者；子 Agent 只写自己独占的评审片段，避免多个 Agent 同时改状态。开始时执行：

```bash
python3 <skill>/scripts/project_state.py <项目>/state.json init
```

默认累计自主执行预算30分钟，每项最多3个内容不同的候选（首版+2轮返修）；自查改动也计数。不是承诺30分钟完成整套。用户已明确给定其他时间预算时，init附--budget-minutes实际分钟数，不能反复新建状态、改素材名称或重置时间来逃避限制。等待用户回复期间先pause，不计入自主执行时间。

每次重建前检查status；候选生成后、评审前记录实际文件哈希。工具记录的是已发生的候选，不是生成器拦截钩子，因此主 Agent 必须在生成前检查版本数，不在第四次生成后才发现超限。

```bash
python3 <skill>/scripts/project_state.py <项目>/state.json status
python3 <skill>/scripts/project_state.py <项目>/state.json candidate --asset 'stickers/收到.gif' --file <候选>/收到.gif
```

素材名使用最终manifest中的语义路径，候选实际文件用新路径。所有阶段保持同一逻辑素材名。每次更改都记录，包括改变节奏、描边、尺寸或编码；字节相同不增加版本。超过预算或次数时保存断点，报告已完成、阻碍和继续所需工作，停止自动制作；用户明确继续后才扩展。已有授权范围内的普通局部修复不反复询问许可。

## 评审任务与落盘

单次评审最多3项，独占任务ID和目录。整套横向关系另做一次批次记录，不重新逐张全评。每评完一项立即写一个完整JSON片段，不等三项全部完成才写。路径用真正的绝对路径，不把“ROOT”占位符原样传给执行工具。评审输入明确给出已验证的Python解释器和工具可用性；若子Agent环境不同，启动时重新验证。

```bash
python3 <skill>/scripts/project_state.py <项目>/state.json review-start --task-id r1 --names 'stickers/收到.gif' 'stickers/好的呢.gif'
# 子Agent立即保存 part-1.json；主Agent校验并留存原文、记录进度：
python3 <skill>/scripts/project_state.py <项目>/state.json review-progress --task-id r1 --file <评审>/part-1.json --manifest <项目>/delivery/manifest.json
```

每个任务5分钟上限，2分钟没有新的逐项结果先查宿主任务状态。等待分成不超过60秒的区间；每次等完运行status或读取新片段。2分钟无进度不能自动起同样的新任务；5分钟到时中止任务，保存已写结果并停止该路线。不能仅向子Agent提示“5分钟内完成”就当作已有超时机制。保存进度后可结束未完成任务：

```bash
python3 <skill>/scripts/project_state.py <项目>/state.json review-stop --task-id r1
python3 <skill>/scripts/project_state.py <项目>/state.json pause
```

中断后重新读取state、原始片段、manifest和当前字节；仅恢复未完成项。review-progress校验片段结构和哈希，不把blocked当作质量失败，也不自动重画。更正有误的评审需新任务和新片段，保留旧记录。

明确继续时记录用户真实授权，不替用户写授权：

```bash
python3 <skill>/scripts/project_state.py <项目>/state.json resume --authorization '用户明确继续的原文'
# 仅用户明确允许某项额外返修时附 --asset 'stickers/收到.gif'，该项追加2个候选名额。
```

## 收尾与过程目录

阻断缺陷进入revise；不影响通过的建议放suggestions，不自动处理。通过后不再为追求更高分修改文件。最终文件先复制到delivery，重新计算哈希并与已评审候选逐项对比；检查复制命令退出码，不能仅看命令发起成功。复制失败就停止收尾，不靠后续评审替它发现。

使用评审汇总器和受检打包器，不临时编写给报告补分、清空unchecked或补true的脚本。最终freeze时重新执行完整打包前检查，并核对state记录的每项当前哈希；正式ZIP仍只通过package_reviewed.py生成。freeze只是操作状态，不是文件系统写保护，打包会再次核对字节。

```bash
python3 <skill>/scripts/project_state.py <项目>/state.json freeze --manifest <项目>/delivery/manifest.json --file <项目>/reviews/final.json
```

每个素材使用独立构建目录，不为改一张重建整套。导出器继续拒绝覆盖旧目录；不用危险覆盖来解决文件堆积。预算内保留参考源、当前候选、最近上一版及对应评审。更旧的可重建临时构建在通过后列出清理范围，按用户已有授权处理；不删除用户源图、唯一动画源、评审证据或继续使用的候选。未获清理授权则保留并报告体积，不自动增加生成轮次。
