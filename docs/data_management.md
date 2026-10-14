# 数据和中间结果的管理规则

项目把 Git 中的可复现记录与本地大型数据分开放置。当前没有预设共享云盘或下载地址；原始数据由用户本地提供。

| 位置 | 内容 | Git 同步方式 |
|---|---|---|
| data/raw/ | 原始 CSV | 文件本身忽略；来源、大小和 SHA-256 记入 data/catalog |
| data/interim/ | 大型中间表 | 文件本身忽略；登记生成命令和校验清单 |
| data/processed/ | 标准化 Parquet 等数据 | 文件本身忽略；登记生成命令和校验清单 |
| data/catalog/ | 数据文件的 JSON 校验清单 | 提交到 GitHub |
| data/summaries/ | 小型中间统计表、CSV | 每个文件不超过 10 MiB，提交到 GitHub |
| outputs/reports/ | 报告、JSON、CSV 汇总 | 每个文件不超过 10 MiB，提交到 GitHub |
| outputs/figures/ | 图表和截图 | 每个文件不超过 10 MiB，提交到 GitHub |
| .cache/、.venv*/ | 运行缓存和虚拟环境 | 忽略，可重新生成 |

10 MiB 是本项目的小型交付文件规则。登记脚本生成的是元数据，不会把文件内容上传，也不会建立云盘。GitHub 本身的大文件限制参见 [官方说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。

## 原始数据

当前 data/raw/user_behavior.csv 是指向用户原始文件的本机链接。另一台电脑需要自行提供相同内容的 CSV，并通过 --data、USER_BEHAVIOR_CSV 或默认路径接入。

运行 benchmark 会计算原始文件的 SHA-256，并保存 data/catalog/user_behavior_raw.json。sha256 可以确认另一台机器的文件内容与本次输入一致。

```bash
bash scripts/run_project.sh verify --manifest data/catalog/user_behavior_raw.json --path /完整路径/user_behavior.csv
```

## 以后产生的大型数据

把实际文件保存到 data/interim/ 或 data/processed/ 后，登记生成方式：

```bash
bash scripts/run_project.sh register --path data/processed/example.parquet --name example_processed --kind processed --recipe '生成该文件的实际命令和参数'
```

若已经有团队授权的共享位置，附加 --share-location 并填写可供交付接收者访问的位置。不要填写密码、访问令牌或带密钥的下载链接。没有提供共享位置时，清单会明确标记 local_only；接收者需使用生成命令重建或另行取得输入文件。

大文件有了共享位置后，更新清单并同步 GitHub。数据的实际共享权限仍由团队指定的存储管理。

## 每次推送前

```bash
bash scripts/run_project.sh check-git
```

命令检查当前 Git 跟踪（含已暂存）的文件，拒绝超过 10 MiB 的文件、原始/大型数据目录的内容，以及本机符号链接。新增文件先暂存再执行该命令，检查通过后提交和 Push。


## 编码规范与数据的关系

CSV 的五个现有字段已经采用 snake_case：time、user_id、item_id、item_category、behavior_type。编码规范规定的是程序与工程管理，没有定义去重、缺失值填充、时间转换或行为编码映射，因此本次保持原始值和文件字节不变。

后续新增代码、内部字段、清单键和数据产物名称统一用 snake_case；读取时继续把 ID 和原始行为值作为 Arrow 字符串保存。若分析阶段需要清洗，必须说明业务规则，把结果写到 data/interim 或 data/processed，并登记来源、生成参数和 SHA-256。不要把原始文件覆盖成清洗结果。

原始数据的内容校验、列名和本次读取证据见 outputs/reports/coding_standard_data_validation.json。Git 只同步清单和小型报告。
