"""Explain persisted transformation fields without changing feature calculations."""


def feature_window_label(days: int | None) -> str:
    """Describe a fixed window or a field-specific historical scope.

    Args:
        days: Fixed historical length, or None for field-specific definitions.

    Returns:
        Chinese window description without a misleading missing-day count.
    """
    return str(days) + "天" if days is not None else "按字段定义的历史或截点"


def explain_feature(name: str, calculation: str) -> str:
    """Resolve intermediate aliases and frozen-model operations for the dictionary.

    Args:
        name: Actual globally unique feature name.
        calculation: Registered expression used by the producer.

    Returns:
        Calculation details that can be read without opening intermediate SQL.
    """
    expressions = {
        "current_streak": "历史7天活跃日期去重，取结束于截点前一天的连续日期段长度；无则0",
        "max_streak": "历史7天活跃日期去重，按相邻自然日连接，取最长连续段长度；无则0",
        "flagged_hours": "历史7天按用户小时加总原记录raw_count，统计合计>90的小时数量",
        "max_hour_count": "历史7天各用户小时原记录量的最大值",
        "purchase_days": "历史30天购买行为记录对应的不同自然日期数",
        "hour_sin": "SUM(sin(2*pi*小时/24)*该小时四元组量)/SUM(该小时四元组量)，历史7天",
        "hour_cos": "SUM(cos(2*pi*小时/24)*该小时四元组量)/SUM(该小时四元组量)，历史7天",
    }
    named = {
        "user_svd_norm": "sqrt(SUM_k(user_svd_k^2))，用户冻结投影向量的L2范数",
        "item_svd_norm": "sqrt(SUM_k(item_svd_k^2))，冻结商品向量的L2范数",
        "user_svd_known_pair_share_7d": (
            "历史7天词表内不同用户商品对数/历史7天全部不同用户商品对数；无历史置0"
        ),
        "user_svd_has_known_history": "历史7天至少有一个商品在冻结词表内为1，否则0",
        "item_svd_known": "商品存在于训练期冻结商品词表为1，否则0",
        "pair_svd_dot": "SUM_k(user_svd_k*item_svd_k)，未知商品坐标按0处理",
        "pair_svd_cosine": (
            "pair_svd_dot/(user_svd_norm*item_svd_norm)，裁剪到[-1,1]；分母0或未知置0"
        ),
        "pair_svd_available": "用户历史至少有一个词表内商品且候选商品在冻结词表时为1",
        "pair_cooc_neighbor_count": "用户历史7天商品中，存在指向候选商品冻结规则的商品数；无则0",
        "pair_cooc_mean_cosine": (
            "匹配规则的平均余弦；每条规则=共同用户数/sqrt(源商品用户数*目标商品用户数)"
        ),
        "pair_cooc_rule_mean_confidence": "匹配规则平均置信度；每条规则=共同用户数/源商品用户数",
        "pair_cooc_rule_max_lift": (
            "匹配规则最大lift；每条规则=置信度/(目标商品用户数/训练用户数)；无则0"
        ),
        "pair_cooc_graph_known": "候选商品在达到训练支持门槛的冻结共现商品集合内为1，否则0",
    }
    if name in named:
        return named[name]
    if name.startswith("user_svd_") and name.rsplit("_", 1)[1].isdigit():
        return (
            "用户过去7天浏览/收藏/加购/购买四元组数按1/2/3/4加权，log1p后乘冻结IDF，"
            + "按用户L2归一化，再乘冻结SVD.components_.T，取第"
            + name.rsplit("_", 1)[1]
            + "维；词表、IDF、分解矩阵均只在首个截点前拟合"
        )
    if name.startswith("item_svd_") and name.rsplit("_", 1)[1].isdigit():
        return (
            "取训练期冻结SVD.components_中该商品列的第"
            + name.rsplit("_", 1)[1]
            + "维；未知商品置0，并结合item_svd_known解释"
        )
    return expressions.get(calculation, calculation)
