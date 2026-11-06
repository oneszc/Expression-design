# 评审片段、人工验收与受检打包

新项目采用schema 2。评审Agent逐项写原始JSON，主Agent使用随附工具校验、汇总，不手工重抄分数。原始片段、人工确认和派生报告均留本地；ZIP只装清单与最终素材。预算与断点操作见 [执行与收尾](runtime.md)。

## 逐项原始片段

一个片段通常只含刚评完的一项，顶层schema_version为2、items为列表。方向草样stage=draft，正式素材stage=final；草样可以校验和汇总，但不能作为正式打包依据。单项如下（仅结构示例，不是真实评分）：

```json
{
  "schema_version": 2,
  "items": [{
    "file": "stickers/收到.gif",
    "sha256": "评审前实际读取文件的64位SHA-256",
    "reviewer_id": "实际评审者ID",
    "stage": "final",
    "scope": "frames",
    "decision": "blocked",
    "total": null,
    "scores": {"identity": 24, "expression": 22, "craft": 30, "legibility": 14},
    "evidence": {
      "identity": "与参考相比的实际观察",
      "expression": "具体帧中动作如何表达需求",
      "craft": "全部解码帧的姿态、接触和稳定性；尚未观察连续播放",
      "legibility": "240px和浅深底实际所见"
    },
    "checks": {"light": true, "dark": true, "all_frames": true, "playback": false},
    "critical_issues": [],
    "unchecked": ["playback"],
    "suggestions": []
  }]
}
```

四维上限25/25/35/15；表达至少18、合计>80。缺观察不能填满分或零分。**只有缺播放这一项，且全部解码帧、浅深底已观察时**，可用scope=frames保存逐帧暂评分（含craft的静帧判断），total=null、decision=blocked。暂评分不代表原速节奏通过。人工播放通过后，汇总器才结合这份暂评分判断是否达到交付条件；报告明确区分观察来源。

缺深底、全帧等其它必要观察时，craft和total为null，decision=blocked，unchecked准确列出缺失检查键。人工播放确认不能补这些缺项。发现真实缺陷写critical_issues；观察不全时仍保留缺陷，但先blocked，不能盲目重生成。检查完整后，有关键缺陷或分数不足必须revise；否则pass。检查齐全时，非阻断建议只写suggestions，不叫“必须返修”。

静态要求light/dark，不需all_frames/playback。banner/cover/icon分别增加checks.banner_design/cover_design/icon_design=true及非空platform_evidence，具体核对见 [微信交付要求](wechat-delivery.md)。不能自动补这些字段。GIF若评审Agent确实能看原速两轮，可直接scope=full、checks.playback=true、非空playback_evidence、无unchecked；不得假称看过。

保存后立即校验，可对不完整整套中的单项执行：

```bash
python3 <skill>/scripts/review_records.py <项目>/delivery/manifest.json --fragments <评审>/part-1.json --check-only
```

退出0只表示片段结构、当前哈希有效，不代表pass；输出remaining给出尚缺评审项。发现pass与缺观察冲突时，退回评审者修正记录，不重画素材。

## 原速预览与人工验收

在用户已接受人工播放路线，或明确要求待验收预览后生成：

```bash
python3 <skill>/scripts/preview_pack.py <项目>/delivery/manifest.json --output-dir <项目>/previews/验收-01
```

输出index.html、实际素材字节副本、最终解码的浅深底全帧图、status.json、playback-pending.json，以及明确命名的“待验收预览.zip”。预览并非合格交付包；包含状态和过程对照，不能重命名冒充合格包。页面没有自动签收功能；浏览器打开成功不等于已观察播放。浏览器决定实际播放调度，原速指不人为更改GIF时间线。

用户逐张在浅/深底至少看两轮并明确确认后，将playback-pending.json另存为新的验收记录，填真实observer、confirmed_at、user_confirmation原文；每项填写loops≥2、light/dark=true、decision=pass及具体evidence。已有file/sha256必须保持与所看快照一致，不重新计算当前文件哈希替换旧快照。仅笼统“看起来不错”且验收范围不明时，不能推定全部两轮验收。文件改变后只让变更项的旧确认失效。

验收记录结构：schema_version=1、observer_type=human、observer、confirmed_at、user_confirmation、items；每项为file、sha256、speed=1、loops、light、dark、decision、evidence。工具可以验证字段与对应关系，不能认证用户真的看过；主Agent必须依据实际用户回复记录，不能代签。

## 整套横向记录

逐项完成后独立评审整套关系；未变素材复用对应哈希的片段，不全套重打分。batch.json结构：

```json
{
  "reviewer_id": "实际横向评审者",
  "manifest_sha256": "当前manifest原始字节SHA-256",
  "asset_hashes": {"stickers/收到.gif": "该文件哈希；这里必须列出全部表情及三张配套图"},
  "batch": {"score": 86, "decision": "blocked", "critical_issues": [], "unchecked": ["playback"], "evidence": "实际横向比较的依据"}
}
```

未看播放时只可将playback留在批次缺项；逐项未完成不冒称整套已完成。已有用户确认与文件对应时可由工具合并。批次阈值同样>80，无85分内部线。修改名称/介绍后需核对语义并更新manifest绑定；只是改元数据不要求重新观看未变图片。修改素材后重评该素材与受影响的整套关系，并更新batch的完整哈希集合。

## 汇总与打包

```bash
python3 <skill>/scripts/review_records.py <项目>/delivery/manifest.json --fragments <评审>/part-1.json <评审>/part-2.json --batch <评审>/batch.json --acceptance <评审>/人工播放确认.json --output <项目>/reviews/final.json --summary <项目>/reviews/汇总.md
python3 <skill>/scripts/package_reviewed.py <项目>/delivery/manifest.json <项目>/reviews/final.json --output <项目>/表情包-合格版.zip
```

fragments应完整列出最终采用的片段路径（每项恰好一次），示例两项不代表正式清单可以缺项。不需人工验收时省略acceptance。汇总器支持保存blocked报告，ready=false不代表可以正式打包；原始片段原文嵌入provenance，分数和缺项不被改写，Markdown由程序生成。

只有明确匹配哈希的人工播放确认，才能在派生视图补齐playback；不会修改原始blocked片段，也不会清除dark、all_frames或平台检查缺项。整套与单项达到门槛才ready。不要临时写合成脚本“补true”“清unchecked”或将当前哈希贴到旧分数上。

打包器重建schema 2派生结果，核对分数、缺项、原始片段、人工验收与当前文件；仍内部执行真实规格校验并打包同一份字节快照。任何失败退出1且不创建ZIP；既有ZIP不覆盖。不会包含原图、密钥、评审或过程文件。保留schema 1历史完整评审兼容，但新项目不使用旧结构规避来源检查；旧记录缺证据不能被新工具自动补成合格。

这些工具不认证评审者身份、不验证人类观察真假，也不能强制宿主调用本流程；不能把程序通过当作审美或微信审核保证。
