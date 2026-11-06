# Rime 词库工具

小狼毫（Rime）86 五笔的桌面小工具：查词、自定义编码、调整候选顺序、编辑上屏联想。

使用 Python 3.11 标准库和 Tk，只支持 Windows。

## 功能

- **查词**：同时查基础码表、个人词典、自定义短语和已学习的词。
- **自定义编码**：写入 `custom_phrase.txt`，有重码时提醒。
- **自动编码**：编码留空时按 86 五笔规则生成，写入 `wubi86_personal.dict.yaml`。
- **调序**：把某个词排到该编码首位。原码表不会被修改。
- **联想编辑**：指定前词后面优先显示的词，调整词库联想的顺序，也可以隐藏词库里的词。词库文件只读，调序靠把相关的词写入“我的联想”实现。内容保存在 `predict_user.tsv`。
- **备份**：每次保存前，把原文件备份到 `backups/`。

已学习的词只能查看，因为它们存放在 Rime 正在使用的数据库里。

## 前提

- 已安装小狼毫。工具从注册表读取用户目录和安装位置。
- 方案为 `wubi86`，并使用个人词典 `wubi86_personal`、快捷短语 `custom_phrase`。
- 使用联想编辑功能时，已经启用 [librime-predict](https://github.com/rime/librime-predict) 和联想词库。

## 安装

1. 把 `rime_files/lua` 里的 `predict_user_filter.lua` 和 `predict_period.lua` 复制到 Rime 用户目录的 `lua` 文件夹。
2. 在 `wubi86.custom.yaml` 的 `patch:` 下加入：

   ```yaml
   "engine/filters/@next": lua_filter@*predict_user_filter
   "engine/processors/@before 1": lua_processor@*predict_period
   ```

   第二行让联想状态下的句号直接上屏，否则句号会被默认的翻页键吃掉。

3. 如果用 Syncthing 同步用户目录，又不想同步联想内容，先把 `/predict_user.tsv`、`/lua/predict_user_filter.lua` 和 `/lua/predict_period.lua` 加入忽略规则。
4. 重新部署小狼毫。
5. 运行工具：从 Releases 下载 ZIP，解压后双击 `RimeDictTool.exe`。也可以从源码运行：

   ```bash
   pythonw rime_dict_tool.pyw
   ```

EXE 没有代码签名，Windows 可能显示安全提示。备份保存在 EXE 旁边的 `backups` 文件夹，所以要解压到有写入权限的位置。

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name RimeDictTool rime_dict_tool.pyw
```

## 显示词库现有联想（可选）

“词库现有联想”列表读取 `data/predict-zhs.tsv`。这个文件来自 [rime-predict-zh](https://github.com/kenspc/rime-predict-zh)，许可证是 GPL-3.0，不包含在本仓库里，需要时自行下载到 `data` 文件夹。

没有这个文件时工具也能运行，只是这个列表为空。

## 测试

```bash
python -X utf8 test_core.py
```

测试在临时副本上运行，不改动正在使用的 Rime 文件。测试需要本机已有 Rime 词库文件，界面测试还需要上面的 `predict-zhs.tsv`。
