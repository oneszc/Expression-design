# 微信交付基线

此配置来自用户于 2026-10-27 提供的微信“表情图片素材概览”截图。该图列出的要求如下；它是本项目已选交付基线，不宣称已实时核实官方全部投稿规则。

| 素材 | 数量 | 格式 | 尺寸 | 大小上限 |
|---|---:|---|---|---:|
| 表情图 | 8～24 | 静态 PNG/JPG/GIF；动态 GIF | 240×240 | 500KB |
| 详情页横幅 | 1 | PNG/JPG | 750×400 | 500KB |
| 表情封面图 | 1 | PNG | 240×240 | 500KB |
| 聊天面板图标 | 1 | PNG | 50×50 | 100KB |

整套名称是用户额外确定的必交付项。截图没有说明名称字数限制、背景和描边细则，不自行编造为平台要求。透明背景、循环时长等制作建议在相应制作参考中说明。

官方核对入口：[微信表情开放平台](https://sticker.weixin.qq.com/)、[制作指引](https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=guide/index.html#/makingSpecifications#specifications_stickers)。制作正式投稿素材前尝试读取当前规则；页面不可读时说明使用本基线，并在当前上传页可用时复核。已有用户当前规格就优先使用，不根据第三方教程悄悄替换。首版编写时官方指引未能读取，未追加猜测规则。

校验器 profile 名为 `wechat-user-2026-10-27`。为保守处理 KB 单位，脚本用 1000 字节/KB；不是推断官方单位定义。未来规则改变时显式修改 profile 和本文件，不能仍用旧报告称当前官方规则通过。

## 清单

`delivery/manifest.json` 是真实最终文件清单，不创建指向不存在素材的伪完整清单。字段如下，省略号只用于此处说明，不写入实际 JSON：

```json
{
  "profile": "wechat-user-2026-10-27",
  "name": "慢半拍小团子",
  "name_status": "confirmed",
  "mode": "static",
  "count": 8,
  "stickers": [
    {"file": "stickers/收到.png", "meaning": "收到", "text": "收到"}
  ],
  "banner": "banner.png",
  "cover": "cover.png",
  "icon": "icon.png"
}
```

实际 `stickers` 数组必须列全 8～24 张，与 `count` 一致。`mode` 为 `static` 或 `animated`；`name_status` 为 `confirmed` 或 `provisional`。每张必有不空的 `meaning`，`text` 可为空字符串。所有路径相对 manifest 所在目录，不接受绝对路径、目录外路径或重复引用。动态表情主图应有至少两个不同帧并无限循环；横幅、封面和图标为静态。

表情文件按聊天含义命名，例如 `周一开机失败.gif`，不使用纯编号或默认编号前缀。名字可以与 `meaning` 一致，也可以压缩成长短适合的短语；不要求图中出现同样的文字。同名使用动作/语气后缀区分，不覆盖已有文件。清理首尾空白以及 `/`、`\`、`:`、`*`、`?`、`"`、`<`、`>`、`|` 等跨平台不适合的文件名字符，清理后再次检查空名称和重名。序号用于表达清单的排序，文件顺序由 manifest 的数组表达，不依赖文件名。该命名约定是 Skill 的交付规则，不冒充微信平台规定；校验器仍可读取旧的编号清单。

```bash
python3 <skill目录>/scripts/validate_pack.py <项目>/delivery/manifest.json --report <项目>/validation.json
```

退出码 0 表示符合本文件的可机械检查项；1 表示发现错误或无法检查。命令参数错误返回 2。`warnings` 包括暂定名称、透明度等仍需人工确认的项目。校验器不会修改图片，不会上传微信，不会创建压缩包。报告文件不覆盖写入；修复后复检时使用新报告路径，例如 `validation-2.json`。

最终压缩包只包含 manifest 列明的最终素材与 manifest 本身；过程参考图、个人源照片、项目记录和校验报告在包外保留。未通过的素材继续修复；若环境能力不足，交付现有产物并列明缺项，不称为完整可提交素材包。
