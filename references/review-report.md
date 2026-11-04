# 评审报告与受检打包

最终交付报告保存为项目 `reviews/轮次/final.json`，由实际独立评审结果形成；不改变 delivery/manifest.json 的字段。报告文件及过程素材留在本地，不随交付ZIP或Skill发布。

## 固定格式

顶层字段：

- `schema_version`：1。
- `reviewer_id`：实际独立评审 Agent 标识。多轮时保存各轮原报告；此字段标识本次逐项结果整合后的最终核验 Agent，不冒领其他人的观察。
- `manifest_sha256`：当前manifest原始文件字节的SHA-256；改语义、配字、名称、路径或顺序后，都需重新核验并更新整体报告。
- `items`：完整列出manifest中的每张表情及banner/cover/icon，恰好各一次，不含额外文件。
- `batch`：整套评审，包含整数`score`（0～100）、`decision`、`critical_issues`、`unchecked`及文字`evidence`，须>80、pass、两项清单为空且证据不空。

每个items条目的格式如下。这是单项结构示例，正式报告必须列全所有素材；分数和证据必须来自实际评审，不能复制示例为真实结果：

```json
{
  "file": "stickers/收到.gif",
  "sha256": "填写该文件原始字节的SHA-256",
  "stage": "final",
  "decision": "pass",
  "scores": {"identity": 24, "expression": 22, "craft": 30, "legibility": 14},
  "evidence": {
    "identity": "参考角色与当前画面实际比较的结果",
    "expression": "聊天场景、语气、主题或笑点如何成立",
    "craft": "逐帧与实际播放所见的制作质量",
    "legibility": "实际尺寸的文字、剪影与边缘检查"
  },
  "checks": {"light": true, "dark": true, "all_frames": true, "playback": true},
  "playback_evidence": "说明观察工具、原速至少两轮以及具体转场所见",
  "critical_issues": [],
  "unchecked": []
}
```

`file`与manifest相对路径完全一致，`stage`为final。四维分数必须为范围内整数，满分依次25/25/35/15；脚本自己求和，不信任另写的total。表达至少18且合计>80。

静态素材只要求light/dark；动态表情另要求all_frames/playback和非空playback_evidence。不能为了让脚本通过把未观察写true。证据不足时相关分数null、decision为blocked，并在unchecked记录缺项，脚本会拒绝。有明确问题时decision为revise并写修复建议，返修流程见 [独立评审与返修](review.md)。

## 执行

```bash
python3 <skill目录>/scripts/package_reviewed.py <项目>/delivery/manifest.json <项目>/reviews/轮次/final.json --output <项目>/表情包-合格版.zip
```

脚本先调用validate_pack.py检查实际编码/尺寸/体积/数量与路径，再核对manifest及每个文件哈希、完整评审覆盖、阶段、分数、关键缺陷、必要观察和整套结论。通过后仅打包已核对的manifest与素材字节，不包含评审文件或目录内其他文件；既有ZIP不覆盖。任一检查失败退出码1，验证失败不创建ZIP；命令参数错误为2，通过为0。

这是受检打包入口，不是安装到所有宿主的系统级拦截钩子；Agent仍须按Skill调用它。它能检查报告完整性和文件对应关系，不能鉴别一段观察描述是真是假、证明评审ID真实或自动决定审美分数。实际独立观察仍是必要步骤。脚本警告如名称暂定仍需在交付时说明，不能用程序通过冒称用户已经选名或微信审核通过。

## 最小闭环验证

随附tests/test_package_reviewed.py使用明确标为合成的测试评审，覆盖80/81分边界、关键缺陷、低表达分、缺项/重复项、草稿、整套失败、缺播放观察、旧哈希、规格失败及禁止覆盖。修改文件后旧评审被拦截，更新对应哈希后才打包，这是版本绑定的测试，不是一次真实艺术评审。真实“生成→不合格→重生成→复评通过”仍需实际案例验证，不为测试伪造子Agent签名。
