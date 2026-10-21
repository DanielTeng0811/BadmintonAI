"""Phase 6 固定驗證題組；只供評估選題，不參與 runtime 路由。"""


TEMPLATE_MINIMAL_5 = (1, 3, 9, 14, 80)
TEMPLATE_COMPOSITE_1 = (13,)
TEMPLATE_STRATIFIED_10 = (1, 3, 6, 9, 13, 14, 19, 22, 45, 80)
TEMPLATE_EXPANSION_5 = (31, 32, 44, 47, 54)
TEMPLATE_GENERALIZATION_5 = (38, 49, 53, 55, 61)


VALIDATION_PURPOSES = {
    1: "scalar + text：單一百分比",
    3: "records + heatmap：明示熱區圖",
    6: "records + bar/line：明示一般繪圖",
    9: "table：前中後場得失分比較",
    13: "composite：比例、得分與失誤多輸出",
    14: "records + pie：明示圓餅圖",
    19: "records + scatter：明示散佈圖",
    22: "table/records + line：比分階段趨勢",
    45: "composite：跨場次、跨局多指標統整",
    80: "narrative + text：策略型綜合分析",
}


EXPANSION_PURPOSES = {
    31: "sequence + pie：指定球種後的下一拍反擊分布",
    32: "rally ratio + text：長回合得分率與回合層級分母",
    44: "sequence + table：三拍得分戰術組合 Top 5",
    47: "comparison：雙方球種頻率與得分率",
    54: "composite：一拍得分比例與空間分布",
}


GENERALIZATION_PURPOSES = {
    38: "ratio：總失分母體與對手特定球種直接得分",
    49: "rally outcome：發球事件連結回合得分者",
    53: "streak + sequence：連續得分與常見戰術組合",
    55: "sequence + ratio：特定回擊後下一拍成功率",
    61: "spatial sequence + ratio：四角調動條件與回合勝率",
}


def as_list(question_set):
    """提供可直接貼入 QUESTIONS_TO_RUN 的 list。"""

    return list(question_set)
