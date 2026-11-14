# 当前特征字典

当前唯一人工阅读入口为[Excel字典](../outputs/reports/stage2/feature_dictionary.xlsx)、
[可搜索字典](../outputs/reports/stage2/feature_dictionary.html)和[机器字典](../outputs/reports/stage2/feature_dictionary.json)。

445条源定义（439标量＋6类逻辑序列）全部保留；当前训练期筛选保留207标量。
目标编码与8维类别稀疏预嵌入另列9条表示，不冒充9个新增业务特征；最终矩阵259列。
字典包含源表、含义、公式、窗口、存储、边界、训练缺失率/互信息、筛选状态及当前预处理方法。
原生成器使用的不可变源字典仍保存在feature_system_20261029，供输入指纹与历史产物核验。
