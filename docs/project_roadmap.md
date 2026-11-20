# 项目任务与验收台账

依据用户提供的[原始大纲](requirements/project_brief.pdf)，共17项。状态更新于2026-11-20。
已确认的数据缺失使用代理口径，逐项边界见[第二阶段验收表](../outputs/reports/stage2/requirements_matrix.md)。

| 编号 | 任务 | 当前状态 | 当前证据 |
|---|---|---|---|
| s1_01 | 工程化环境与版本管理 | 完成，持续回归 | [工程说明](stage1_completion.md)、[阶段验收](../outputs/reports/stage1/audit.json) |
| s1_02 | 文献与技术栈储备 | 完成 | [研究目录](research/README.md)、阶段验收内研究检查 |
| s1_03 | 全量加载、清洗与质量分析 | 现有数据规模完成；亿级压力验证待执行 | [清洗规则](cleaning_rules.md)、[重复值政策](duplicate_policy.md) |
| s1_04 | 压缩、Parquet与基础中间表 | 完成 | [预处理规则](preprocessing_rules.md)、[原始测量](../outputs/reports/stage1_step4/README.md) |
| s2_01 | SQLite与SQL基础分析 | 完成 | [方法](sqlite_analysis.md)、[11项结果](../outputs/reports/stage2_step1_20261024/README.md) |
| s2_02 | 全维度特征体系 | 完成 | [特征体系](feature_system.md)、445源定义、四截点预拼接层 |
| s2_03 | 特征预处理与有效性验证 | 主体完成；跨截点稳定性专项待补 | [分组筛选](feature_validation.md)、[编码与稀疏预嵌入](stage2_preprocessing.md)、[全量重放](../outputs/reports/stage2/audit.json) |
| s2_04 | 多维度探索性分析 | 核心完成；在线入口与展示细项已补齐 | [联动看板](eda_dashboard1.md)、[图表和洞察](../outputs/reports/stage2/README.md) |
| s3_01 | 样本与数据划分 | 已完成并复核。7 天对级样本、时间回测、7:2:1 分组分层和不平衡对照一致 | [方法](stage3_sampling.md) · [3.1 复核](../outputs/reports/stage3_traditional_v1/stage31_review.json) · [数据清单](../data/catalog/stage3_samples_v1.json) |
| s3_02 | 传统模型与调优 | 已完成。逻辑回归、XGBoost、LightGBM 基线与 36 次 Optuna 试验。按时间验证 AUC 选型并在完整测试集对比 | [方法](stage3_traditional.md) · [验收](../outputs/reports/stage3_traditional_v1/README.md) · [模型清单](../data/catalog/stage3_traditional_v1.json) |
| s3_03 | 深度模型与优化 | 待执行 | GRU/LSTM、DIN、注意力、训练优化 |
| s3_04 | 融合与解释 | 待执行 | Stacking、系数/SHAP、错误/冷启动/长尾 |
| s3_05 | 业务模拟 | 待执行 | 模拟A/B、收益假设与敏感性 |
| s4_01 | 工程化封装 | 待阶段性收口 | 可复用训练/推理、API文档和示例 |
| s4_02 | 总报告与汇报材料 | 待执行 | 项目总报告、汇报PPT、技术分享PPT |
| s4_03 | 复盘总结 | 待执行 | 问题、解决、局限和优化 |
| s4_04 | 提交与展示 | 待最终交付 | main同步、发布与展示记录 |

2026-11-15严格逐项复核：本轮数值与157项测试均通过；13项技术验收细项中，跨截点特征稳定性专项仍属部分完成。看板的指标卡、周末标识、商品类目列和漏斗比率标注待补。详见[完成与复核报告](../outputs/reports/stage1_stage2_review_20261114_01/completion_report.md)，不以核心产物完成替代所有细项通过。

## 验收顺序

每个小任务核对真实产物、输入指纹、结果和资源记录；第二阶段起回归上一完整阶段。
代码按AGENTS.md检查，完成差异评审后让feature CI通过，再合入dev/main并核对各自CI。
历史测量保留原值；重复报告移出Git的记录见[归档清单](archive_manifest.json)。

## 已接受的数据边界

非隐私、允许公开分析；平台来源许可编号未独立核实。
微软中国业务按Asia/Shanghai假设，源时间保持原值；金额缺失采用RF代理。
没有曝光、订单、分钟秒或会话标识，不构造相应真实指标；期内无法定节假日，不伪造节日对照。

2026-11-17：2.4增加GitHub Pages在线17视图及CSV导出，补齐人均记录、类目覆盖、周末、商品类目与漏斗分母展示。发布清单见outputs/reports/dashboard_publication_20261117/manifest.json；历史2026-11-15复核保留其测量时点结论。
