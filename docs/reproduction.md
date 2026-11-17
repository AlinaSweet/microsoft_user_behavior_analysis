# 运行、复现与核验

所有命令在项目根目录执行。先安装Python3.12并运行bash scripts/setup_environment.sh。
环境锁为requirements*.txt；科学计算依赖均已锁定，不需要为第二阶段安装GPU或深度学习框架。
原CSV位于data/raw/user_behavior.csv，只读；换机器请按configs/dask.yaml或USER_BEHAVIOR_CSV配置原始位置。
大型本地产物不在Git内，依data/catalog的生成关系重建；禁止因缺文件就填造结果。

| 内容 | 入口 |
|---|---|
| 环境/资源 | bash scripts/run_project.sh check；benchmark |
| 清洗/预处理历史基线 | bash scripts/run_project.sh clean；preprocess；具体参数见各方法文档 |
| 数据库 | bash scripts/run_project.sh database，参数见sqlite_analysis.md |
| SQL | PYTHONPATH=src .venv/bin/python scripts/run_sql_analysis.py |
| 全记录特征 | PYTHONPATH=src .venv/bin/python scripts/run_features.py --phase all |
| 预拼接审计 | scripts/audit_wide_features.py，参数见prejoined_features.md |
| 对级标签与第一轮筛选 | scripts/run_feature_validation.py，参数见feature_validation.md |
| 当前新增预处理/实验/报告/重放 | PYTHONPATH=src .venv/bin/python scripts/run_stage2_completion.py --phase all |
| 本地交互EDA | bash scripts/run_eda_dashboard.sh |
| GitHub在线EDA | https://alinasweet.github.io/microsoft_user_behavior_analysis/ |
| 生成静态发布目录 | PYTHONPATH=src .venv/bin/python scripts/build_dashboard_site.py |
| 全部代码检查 | bash scripts/check_quality.sh --force |

不同版本必须复制对应config并设置全新的输出目录/catalog，然后用--config指定。
已登记当前版本不允许原地重建；流水线拒绝覆盖，避免改写测试结果或历史证据。
第二阶段新流程顺序为prepare→experiments→reports→audit；报告读取data/summaries/eda_support_v1的冻结补充证据。
分组相关性用最多100,000条训练候选的确定性样本；模型训练与矩阵/预测核验覆盖完整候选。
补充证据CSV与feature_evidence.json来自已验收全量EDA，manifest给出来源提交与SHA；它们不参与模型拟合。

Excel使用scripts/export_current_dictionary.mjs和@oai/artifact-tool制作，参数为项目根目录与本地预览目录，
需该JS包的已配置运行时。JSON/CSV、计算和看板不依赖Excel生成环境。
第一阶段新复核须使用未存在目录：

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_stage1.py \
  --output-dir outputs/reports/stage1_audit_YYYYMMDD_NN
```

完整数据控制：scripts/audit_current_data.py；原特征工件：scripts/audit_feature_delivery.py。
它们不改变原CSV、特征数值或标签；新输出与当前catalog指纹有变更时必须登记为新版本。
