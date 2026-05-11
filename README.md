# ctx-keeper

Codex 多 profile 切换时，侧边栏历史全部消失——这是 `state_5.sqlite` 里 `model_provider` 字段的过滤问题，不是数据丢失。ctx-keeper 在切换时同步更新这个字段，历史始终可见。顺带提供跨三个 Codex profile + Claude Code 的统一对话历史面板。

![Screenshot](assets/screenshot.png)

## 功能

- **切换不丢历史**：`ctx switch` 在替换 `auth.json` 和 `config.toml` 的同时，把 `state_5.sqlite` 里所有 thread 的 `model_provider` 更新为当前 profile，Codex 侧边栏立刻能看到全部对话
- **跨 profile 续接对话**：对话内容存在 `sessions/` 的 jsonl 里，切换后用新 provider 继续读，不再因 provider 不匹配打不开
- **统一历史面板**：TUI 聚合 codexapis / toskaxy / chatgpt 三个 profile 和 Claude Code 的对话，按时间倒序、支持全文搜索
- **StatusLine 集成**：`ctx setup` 自动写入 Claude Code 和 Codex 的 statusLine 配置，状态栏实时显示当前 profile

## 安装

**一键安装：**

```bash
curl -sSL https://raw.githubusercontent.com/1614080902102/ctx-keeper/master/install.sh | bash
```

**手动安装：**

```bash
git clone https://github.com/1614080902102/ctx-keeper.git
cd ctx-keeper
pip install -e .
ctx setup
```

`ctx setup` 会配置 Claude Code 和 Codex 的 statusLine，状态栏显示当前 profile 名称。

**VSCode 扩展（可选）：**

在状态栏显示当前 profile + 今日 token 用量，点击切换。

```bash
cd vscode-extension
npm install && npm run compile
npm install -g @vscode/vsce
vsce package --no-dependencies
code --install-extension ctx-keeper-0.1.0.vsix
```

Reload Window 后状态栏出现 `⊙ <profile>  <今日用量>` 即为成功。

## 用法

### 切换 profile

```bash
ctx switch codexapis        # 切换到指定 profile，同步更新 state_5.sqlite
ctx switch toskaxy
ctx switch chatgpt

ctx switch --list           # 列出所有可用 profile
ctx switch --current        # 显示当前 profile 名
```

### 浏览对话历史

```bash
ctx                         # 打开交互式 TUI，列出所有对话
ctx show <session-id>       # 查看某条对话完整内容
ctx search "关键词"          # 全文搜索所有对话
```

### 用量统计

```bash
ctx stats                   # 今日 token 用量汇总
ctx stats --week            # 最近 7 天按日汇总
```

## 原理

Codex 的 `state_5.sqlite` 里，每条 thread 有 `model_provider` 字段，侧边栏按这个字段过滤显示。从 `codexapis` 切到 `toskaxy`，旧对话的 `model_provider` 还是 `codexapis`，所以 UI 不展示它们——数据没丢，只是被过滤掉了。

`ctx switch` 切换时额外执行一条 SQL：`UPDATE threads SET model_provider = ?`，把所有 thread 的 provider 改为新 profile 的值。对话内容本身存在 jsonl 文件里，不受影响，新 provider 可以直接读历史上下文接着聊。

## 致谢

数据读取思路参考了 [stormzhang/token-tracker](https://github.com/stormzhang/token-tracker)，代码从零实现。

## License

MIT
