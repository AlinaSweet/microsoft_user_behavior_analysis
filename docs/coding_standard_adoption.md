# 编码规范落地说明

本次依据 docs/standards/coding_standard.pdf 整改。后续协作入口为仓库根目录 AGENTS.md；编码规范原文保存在 docs/standards，便于换机器后继续执行。

| 原文范围 | 本项目落实方式 |
|---|---|
| 总则、格式、命名 | Black 88 字符、4 空格、双引号、snake_case、单个末尾换行；.editorconfig 提供编辑器默认值 |
| 导入 | isort 的 Black profile；标准库/第三方/本项目分组，每行一个导入，全部绝对路径 |
| 文档与类型 | 公共模块/类/函数有 docstring；公共函数参数与返回值有类型，配置和报告用 TypedDict，登记请求用 frozen dataclass |
| 异常 | ProjectError 体系；YAML/字节大小解析保留原始异常原因；命令入口记录失败日志；文件和 worker 用上下文管理器 |
| 函数与模块 | 按 api/service/dao/models/common 分层；登记参数封装为对象；函数不超过 5 个参数，模块控制在 500 行内 |
| 性能与安全 | CSV 分块、Arrow 字符串、流式 SHA-256；配置逐字段校验；输出路径和符号链接不得逃出项目目录 |
| 测试 | tests/unit 和 tests/integration；合成数据、独立场景、AAA；真实 worker 和 CLI 报告落盘都有覆盖 |
| 工具和 CI | Black、isort、flake8、mypy、pylint 全部安装并锁版本；统一入口 check_quality.sh；本地 hooks + Quality 工作流 |
| 版本控制 | feature/coding-standard 整改；Conventional Commit；检查和代码复核完成后合入 dev/main |

## 五种工具怎样配合

- Black 整理代码，isort 整理导入；正常检查只报告，--format 才改写代码。
- flake8 使用 .flake8，因为该工具不原生读取 pyproject.toml 配置；E203/W503 与 Black 兼容，E501 按原文交给格式工具和专项检查。
- mypy 检查整个 src/tests/scripts，启用 disallow_untyped_defs；安装 pandas、psutil、PyYAML 的类型存根，没有全局 ignore_missing_imports。
- pylint 要求检查通过且评分 10.00；仅为声明式数据容器关闭 too-few-public-methods，为重复的类型结构/测试准备关闭 duplicate-code。参数、命名、未使用导入等检查保留。
- PDF 专项检查补充禁止隐式字符串拼接、公共 API 文档与类型、裸 except、可变默认值、测试 print、88 字符硬上限等规则。自动工具仍不能完全判断业务正确性，需要评审。

## 本次代码复核

本次由执行改造的助手对差异进行复核，没有引入独立人工审批。复核重点及处理结果：

1. 保留已有 runtime.py、artifacts.py 的导入位置，现有命令仍由 run_project.sh 调用。Python 登记接口按参数上限要求改为 register(ArtifactRequest(...), root=...)；命令行 register 参数不变。
2. 输入路径按项目根目录解释，允许原有只读数据软链接；输出路径解析软链接后必须留在项目内。
3. 配置先校验结构和具体值，再构建类型记录；禁止布尔值充当 worker 数、未知编码、无效字节大小和乱序内存阈值。
4. 测量服务只返回数据，报告保存由数据访问层处理；测试不会覆盖真实数据清单或历史报告。
5. benchmark 指纹记录实际生效的配置，以排序 JSON 计算并注明口径，避免把默认文件的指纹冒充自定义配置。
6. 原始 CSV 保持只读接入；用现有校验清单核对大小和 SHA-256，未按编码风格改写业务值。
7. 本地 hooks 和 CI 检查均使用同一入口；缓存只复用同一源码/配置/工具版本成功记录，Git 文件政策每次重新检查。

当前未开启 GitHub 服务端分支保护；代码评审与检查通过是项目合入约定。若将来增加团队成员，可由仓库管理员结合账号权限设置强制保护规则。

## 后续新增内容的要求

新增代码先确定所属层，补 docstring/类型和对应场景测试，再执行 `bash scripts/check_quality.sh --format`。查看差异与检查结果后提交到 feature 分支，确认 GitHub Actions 的 Quality 成功，再评审合入 dev/main。

框架要求的 setUp/tearDown、__main__、Git hook 文件名，以及真实包名/worker 地址等外部事实名称保留原样。所有业务数据转换另存新产物并记录规则，不覆盖原始数据。

检查结果见 outputs/reports/coding_standard_compliance.json；原始数据校验及运行证据见 outputs/reports/coding_standard_data_validation.json。历史工程测量结果保留原记录。
