# 当前结果索引

| 内容 | 位置与作用 |
|---|---|
| 第一阶段当前复核 | [stage1/audit.json](stage1/audit.json)，本轮重新执行 |
| 第二阶段主交付 | [stage2/README.md](stage2/README.md)，当前统一报告、字典、图表、编码及全量重放 |
| 数据库与SQL | [stage2_step1_20261024](stage2_step1_20261024/README.md)，当前SQLite及11项查询基础证据 |
| 重复值保留政策依据 | [duplicate_review_20261024](duplicate_review_20261024/README.md)，用户材料、全量频数与独立核验 |
| 清洗/压缩原始测量 | [stage1_step3](stage1_step3/README.md)、[stage1_step4](stage1_step4/README.md)，历史归并口径作回归对照 |
| 源特征生成 | [feature_system_20261029](feature_system_20261029/README.md)，源字典和生成器输入，保持可核验 |
| 预拼接审计 | [prejoined_wide_20261107](prejoined_wide_20261107/README.md)，四截点全部439标量的连接及逐值控制 |
| 第一轮监督验证 | [feature_validation_20261114](feature_validation_20261114/README.md)，不可变样本、筛选规则、OHE六组实验与指纹 |

根目录的engineering/environment/research/coding报告是基础测量和自动检查摘要。
重复复核尝试、旧看板与制作预览已移至仓库外，见[清单](../../docs/archive_manifest.json)。
