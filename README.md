# 🐴 Jacko Skills

我的个人 AI Agent 技能库 — 收集我在日常工作中制作、打磨并实际使用的 AI 技能（SKILL.md 格式）。

> **Strive for excellence, and success will come along.** — 追求卓越，成功将伴你而行。

## 这是什么？

这是一套遵循 [Anthropic Agent Skills](https://github.com/anthropics/skills) 规范的自制技能集合。每个技能都是带 `SKILL.md` 说明文件的目录，包含明确的触发场景、执行步骤和注意事项，让 AI Agent 在合适的时机自动加载并使用。

## 技能列表

| 技能 | 说明 | 状态 |
|------|------|------|
| （建设中） | 技能将陆续添加 | 🚧 |

## 如何使用

### 方式一：直接复制

将技能目录复制到你的 Agent 技能目录：

```bash
# 以 WorkBuddy / Claude Code 为例
cp -r skills/<skill-name> ~/.workbuddy/skills/
# 或
cp -r skills/<skill-name> ~/.claude/skills/
```

### 方式二：克隆整个仓库

```bash
git clone https://github.com/jackovibe/jacko-skills.git
```

## 技能规范

每个技能遵循以下结构：

```
skills/
└── <skill-name>/
    ├── SKILL.md          # 技能主文件（必填）
    ├── reference/        # 参考资料（可选）
    └── scripts/          # 辅助脚本（可选）
```

`SKILL.md` 使用 YAML frontmatter 声明元数据：

```yaml
---
name: skill-name
description: 何时使用该技能的描述
---
```

## 开源协议

本项目采用 [MIT License](LICENSE) 开源，欢迎 Fork、修改与二次分发。
