# 本项目后续工作规则

本项目执行 docs/standards/coding_standard.pdf 中的编码规范。本文件概括强制要求，不替代原文。

- 所有项目产物保存在此仓库根目录下；原始 CSV 只读接入，业务值转换必须有明确业务规则和新产物。
- Python 使用 4 空格、双引号、88 字符行宽、单个末尾换行。所有字符串续行显式使用 + 或 f-string，禁止相邻字符串隐式拼接。
- 使用 snake_case 命名，类使用 PascalCase，常量使用大写下划线。unittest 的 setUp/tearDown 等框架回调名称是框架要求的例外。
- 标准库、第三方库和本项目导入分组；每个 import 独占一行；只用绝对导入；禁止通配符和循环导入。
- 公共模块、类、函数和方法必须有 Google 风格 docstring；所有公共函数参数与返回值必须有类型注解；复杂记录使用 TypedDict 或 dataclass。
- 函数不超过 5 个显式参数，模块不超过 500 行；内部实现使用单下划线前缀。禁止可变默认参数、裸 except、静默吞错和注释掉的代码。
- 注释解释原因，TODO 必须写 TODO(责任人)。禁止硬编码密钥；路径必须校验；将来 SQL 必须使用参数化查询。
- 使用 api/service/dao/models/common 分层，配置在 config.py；测试区分 unit/integration，采用 arrange-act-assert，每个用例只覆盖一个场景。
- 修改后运行 bash scripts/check_quality.sh；自动格式化运行 bash scripts/check_quality.sh --format。提交前安装并使用 .githooks，本地和 CI 均检查规范、测试和类型。
- main/dev 合入前，必须完成代码评审并让 Quality CI 通过；失败时修正后再合入。Conventional Commits 每次聚焦一个改动。
- 数据字段与生成文件用小写下划线命名。外部真实包名、worker 地址等事实映射键保留原值，避免改变其含义。
- 历史测量报告保留原始结果；新验证记录单独登记。大文件留在规定的数据目录并写清单，小型报告可同步到 GitHub。

- 长期任务范围与验收按 docs/project_roadmap.md：完成每个小任务后复核前序成果；第二阶段起复核上一完整阶段。不得把设计或缺失证据登记为实现完成。
- 数据使用声明、微软中国地区与金额缺失的代理分群，按 docs/business_conventions.md 和 data/catalog/data_provenance.json；模型拟合仍须遵守预测截点和训练期边界。
