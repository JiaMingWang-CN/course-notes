# 课程讲解 HTML / MP4：本地完整技能包的适配入口

**本文件只定义 course-notes 的适配差异，不取代完整版技能。** 全套原始技能正文、references、scripts、示例素材与课程适用的两个完整工作流保存在本仓库 `references/hyperframes-skills/`（来源与 Apache-2.0 许可证见该目录的 `PROVENANCE.md`、`LICENSE`）。执行时只读本仓库内这些文件；`/hyperframes-core` 等名称均映射为 `references/hyperframes-skills/hyperframes-core/SKILL.md`，绝不从用户主目录安装/加载技能。

## 入口及共享制作链

先通过根目录 `SKILL.md` 第 0 步确认输入、画像、交付类型和权限，完成可追溯笔记。然后从本仓库读取 `references/hyperframes-skills/hyperframes/SKILL.md` 的入口合同；课程短篇原创图解参照本地 `faceless-explainer/SKILL.md`，较长课程、含原片剪辑或定制交互参照 `general-video/SKILL.md`。这两个工作流在仓库内，不执行它们原有的全局技能更新步骤；选定后按其引用读取本地完整领域文档，不只读本文件的摘要。课程笔记已提供学习目标与证据，勿重新询问已回答的问题，也勿把 HTML 模板的 `BRIEF.md` 误判为 HyperFrames 工程的 brief。

**相同的能力用于两种输出：**

| 制作阶段 | 本地完整版来源 | 课程适配与统一质量门槛 |
|---|---|---|
| 主题/观众/时长、计划与用户审稿 | `hyperframes`、`faceless-explainer` / `general-video`、`hyperframes-creative` | 脚本与分镜逐段对应笔记证据，术语、公式条件、例题和反例一致；无依据不说“必考” |
| 画面风格、教学结构 | `hyperframes-creative`、`references/STYLE_PROFILE.md` | 默认温和教材；只有字幕不声称看过原片的镜头/音色；需要改风格先征求用户 |
| 场景结构、片段与字幕时间 | `hyperframes-core`、`hyperframes-studio` | 阅读区域、字幕轨、安全区、演示/口播同步；多场景清晰可编辑 |
| 概念动效与可 seek 镜头 | `hyperframes-animation`、`hyperframes-keyframes` | 动效用于解释步骤与状态，避免装饰替代推理；关键状态有足够阅读停留 |
| 命名视觉与转场 | `hyperframes-registry` | 先检索匹配项再决定安装；安装、远程获取与素材许可遵守第 0 步授权 |
| 资产、声音、字幕 | `media-use` | 素材落盘并记录出处/许可；干净字幕与 TTS 表演文本分离；原课程片段不自动获得再发布权 |
| 放置后的混音 | `hyperframes-audio` | BGM 与旁白重叠时让出语音空间并试听；只有真实应用和检查过频段处理才称为 carve |
| 验证/诊断/预览/渲染 | `hyperframes-cli` | 读取相应本地命令合同，报告实际结果，不用过时别名 |

已有的 Fish Audio 仅在用户明确授权时使用；不擅自克隆原讲师声音。实际 TTS/字幕边界优先于脚本中估算的 3:30 时长。只有本地字幕或原片未核实时，标明相应限制。

## 输出适配（制作链相同，交付机制不同）

| 交付 | 末端适配 | 必要验证与批准 |
|---|---|---|
| HTML 交互微课（`--video`） | 保留播放/暂停、跳转、手动演示和可键盘操作的控件。`scripts/generate_hypit_lesson.py` 仅作 HTML 与制作文档起稿；必须按上述同一完整版工作流完成内容、动效、音频和布局，再把需要的能力落实到最终 HTML，而不以“模板不支持”为由省略。若同时制作 MP4，优先共用经核实的脚本、场景素材与可 seek 的合成，再单独加入浏览器交互层；浏览器交互不能反向成为 MP4 帧状态。确实无法实现已确认的能力时先说明并征求用户调整范围。 | 静态核对必做；浏览器审查仅用户明确同意才运行 `audit_player.py`，未运行则标明。不要把播放器当成视频成片。 |
| MP4（`--render-video`） | 小节 `hyperframes/` 内构建可 seek、确定性的工程；交互按钮不能进入渲染关键路径，使用本地音视频素材和明确时轴。CLI 是运行依赖，不是额外技能。 | `npx hyperframes check`、场景快照、最终 Studio 预览；等待用户批准**最终预览**后 `npx hyperframes render`，再用 `ffprobe` 核对流、时长、分辨率并抽听。拒绝验证或未批准只交付工程。 |
| 两者都要 | 共用核实后的笔记、脚本、分镜、场景素材与许可媒体，分别适配交互层和可渲染层；若布局或时间需要独立适配，记录差异，不假称旧模板 HTML 可以无损转换。 | 分别记录 HTML 的浏览器审查状态和 MP4 的 check/预览/批准/渲染状态。 |

技术约束来自完整版 `hyperframes-core/references/`：主合成 `data-composition-id` 与 `data-duration`，片段 `data-start` / `data-duration`，GSAP 使用暂停且注册的时间轴，不依赖实时钟、随机数或点击状态驱动渲染。Studio 分轨、keyframe、音频属性、CLI 参数等细节均以本仓库相应完整版文件为准，**不要从本适配表猜 API**。

## 本地依赖与路径

- 10 个原始领域/入口目录以及 2 个课程所需工作流全部在 `references/hyperframes-skills/`；包内 `../` 相对引用按实际相邻路径解析，`<SKILL_DIR>` 始终是正在执行的**本地副本**目录。原文中以 `/skill-name` 形式引用别的技能，改在该本地目录寻找 `skill-name/SKILL.md`。遇到本包不存在的专项工作流（如 Figma 输入或别的交付类别），不要暗中从系统目录补装；先说明边界并询问用户是否变更任务范围。
- 不运行 `npx hyperframes skills update` 或 `npx hyperframes skills`；CLI `init` 必须设置 `HYPERFRAMES_SKIP_SKILLS=1`（在 PowerShell 使用 `$env:HYPERFRAMES_SKIP_SKILLS='1'`，在 bash 使用 `HYPERFRAMES_SKIP_SKILLS=1`）。保留项目中的 CLI/GSAP 版本及 lockfile；CLI/Node.js 22+/FFmpeg 等**软件依赖**不在技能包中，缺少时先征求安装许可。技能离线可读，不表示首次运行 CLI、使用远程素材服务或渲染在无依赖环境下也能离线完成。
- 对原包的其他更新/安装指令，均以本适配层的“不更新技能”规则优先；CLI 命令合同与素材服务仍以被复制的本地文件为准。来源/修改清单见 `references/hyperframes-skills/PROVENANCE.md`。
