# 第一阶段当前复核

四项任务为工程环境与版本管理、文献与技术栈、全量清洗、压缩与中间表。
本次第二阶段收口后重新执行完整第一阶段审计，入口为[完整证据](../outputs/reports/stage1/audit.json)。

证据含完整质量门禁、真实Dask worker、原始CSV与产物指纹、全部聚合关系、异常阈值和文献检查。
[清洗测量](../outputs/reports/stage1_step3/README.md)与[压缩测量](../outputs/reports/stage1_step4/README.md)保留当时原值。
历史归并事件用作回归对照；当前第二阶段使用全部有效记录，详见[重复值政策](duplicate_policy.md)。

重新核验时必须使用未存在的目录：

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_stage1.py \
  --output-dir outputs/reports/stage1_audit_YYYYMMDD_NN
```

云端分支与CI在第二阶段[交付记录](../outputs/reports/stage2/cloud_delivery.json)单独核验。
旧复核尝试已依[清单](archive_manifest.json)保存到仓库外，不作为当前入口。
