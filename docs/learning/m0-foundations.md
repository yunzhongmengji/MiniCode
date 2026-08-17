# M0：工程基础与 CLI

## 文件地图

- `pyproject.toml`：项目元数据、Python 版本、依赖、构建方式和 CLI 入口。
- `uv.lock`：uv 自动维护的精确依赖版本，不手工编辑。
- `.python-version`：告诉 uv 当前项目选择的 Python 版本。
- `.venv/`：可重建的项目运行环境，不提交 Git。
- `src/minicode/cli.py`：解析命令行参数并返回退出状态。
- `tests/test_cli.py`：CLI 行为的离线自动化测试。
- `.gitignore`：人工维护忽略规则，Git 自动应用这些规则。

## 环境关系

解释器是真正执行 Python 代码的程序；虚拟环境保存项目独有的解释器入口和依赖；uv 选择解释器、创建环境、解析并安装依赖。

`uv sync` 将 MiniCode 以可编辑方式登记到 `.venv`。源码仍在 `src/minicode/`，虚拟环境保存指向源码的登记信息，并根据 `pyproject.toml` 生成 `minicode` 命令。

## CLI 调用链

~~~text
终端输入 minicode run "修复测试" --dry-run
  → Bash 找到 .venv/bin/minicode
  → pyproject.toml 登记的 minicode.cli:main
  → build_parser() 定义命令规则
  → parse_args() 生成 Namespace
  → main() 根据 command 和 dry_run 分支执行
~~~

退出码约定：`0` 成功，`1` 程序未完成任务，`2` argparse 判断命令使用错误。正常结果写入 stdout；错误和诊断信息写入 stderr。

## 测试工具

pytest 自动发现 `test_*.py` 中的 `test_*` 函数。`capsys` 捕获 stdout 和 stderr；`pytest.raises` 捕获预期异常。Ruff 检查常见代码问题并统一格式。

## 信任边界

模型只提出动作，不拥有权限。候选动作依次经过 Schema、Policy、必要的 Approval 和受限 Executor；OS Sandbox 是应用代码同时出错时的最后强制防线。明确越权的动作应由 Policy 直接 Deny，不能依靠 Approval 洗成合法动作。

## 复习题

1. 为什么修改 `cli.py` 无法修复 Hatchling 下载失败？
2. `uv sync`、`.venv` 与可编辑安装分别负责什么？
3. stdout、stderr 和退出码怎样共同构成 CLI 契约？
4. 为什么 Policy 放行后仍需要 Executor 和 OS Sandbox？
