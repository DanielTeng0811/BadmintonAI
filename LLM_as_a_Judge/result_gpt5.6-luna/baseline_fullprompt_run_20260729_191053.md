# baseline_fullprompt_run_20260729_191053

## Run 資訊

```text
目標題數: 40
架構: 第三層 baseline_fullprompt
生成模型: gpt-5.6-luna
裁判模型: gpt-4o-mini
SKIP_INSIGHT: True

總計 Token 消耗統計:
- 總計產出 Token (input): 361,863
- 總計產出 Token (output): 100,365
- 總計評分 Token: 0
- Generation 成本: 0.964053
- Judge 成本: 0
- 總成本: 0.964053
- 項目總計 Token: 462,228
- 洞察 Token (input/output): 0/0
- 評估 gate: code_logic

實際處理題數: 40
逐題生命週期統計:
- completed: 40

題目列表:
- 正確: none
- 錯誤: none
- 未評分: [1, 6, 10, 13, 16, 17, 18, 22, 25, 30, 31, 34, 37, 38, 42, 45, 47, 50, 51, 60, 61, 63, 65, 66, 67, 71, 73, 76, 79, 80, 82, 83, 84, 85, 88, 89, 91, 93, 95, 100]
- 執行失敗: none

各階段 Token:
- step1: input=0, output=0, total=0, calls=0
- code_generation: input=307441, output=89514, total=396955, calls=40
- execution: input=0, output=0, total=0, calls=0
- insight: input=0, output=0, total=0, calls=0
- judge: input=0, output=0, total=0, calls=0
- repair: input=54422, output=10851, total=65273, calls=6

Step 1 metadata routing:
- Q1: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q6: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q10: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q13: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q16: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q17: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q18: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q22: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q25: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q30: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q31: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q34: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q37: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q38: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q42: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q45: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q47: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q50: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q51: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q60: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q61: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q63: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q65: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q66: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q67: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q71: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q73: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q76: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q79: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q80: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q82: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q83: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q84: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q85: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q88: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q89: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q91: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q93: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q95: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none
- Q100: enabled=False, needs_court_info=False, source=step1_disabled, metadata=full_court_place, groups=none

逐題洞察狀態:
- Q1: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q6: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q10: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q13: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q16: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q17: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q18: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q22: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q25: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q30: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q31: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q34: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q37: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q38: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q42: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q45: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q47: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q50: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q51: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q60: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q61: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q63: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q65: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q66: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q67: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q71: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q73: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q76: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q79: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q80: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q82: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q83: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q84: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q85: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q88: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q89: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q91: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q93: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q95: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
- Q100: status=skipped, skipped=True, completion=analysis_complete_insight_skipped, input=0, output=0
```

## 人工複核統計

- 正確題目數：30/40 (75.00%)
- 錯誤題目數：10/40
- 正確題目：[1, 6, 16, 17, 18, 22, 25, 30, 31, 34, 38, 42, 45, 47, 50, 51, 63, 65, 66, 71, 73, 79, 80, 82, 84, 85, 88, 89, 95, 100]
- 錯誤題目：[10, 13, 37, 60, 61, 67, 76, 83, 91, 93]

## 逐題統整

| 題號 | 判定 | 程式執行 | 審核摘要 |
| ---: | --- | --- | --- |
| 1 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 6 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 10 | 錯誤 | 正常 | 把每個周天成前場擊球所在回合的最終勝負回填到該拍，因而將得分回合中的所有前場球都當成得分球種；沒有要求該拍本身為 player == getpoint_player 的主動得分終結拍。 |
| 13 | 錯誤 | 正常 | 把回合最終得分者套到回合內每一拍，導致得分回合中周天成所有擊球都被計為得分、失分回合中所有擊球都被計為失誤，球種得失分次數被重複放大。 |
| 16 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 17 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 18 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 22 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 25 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 30 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 31 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 34 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 37 | 錯誤 | 正常 | 題目要求周天成自己殺球失誤的原因；程式卻分析周天成殺球後對手下一拍失誤的原因，分析主體與事件方向顛倒。 |
| 38 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 42 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 45 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 47 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 50 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 51 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 60 | 錯誤 | 正常 | 只取失分回合倒數第二拍，未限制倒數第二拍 player 為周天成；當最後一拍為周天成失誤時，會把對手的前一拍球種混入結果。 |
| 61 | 錯誤 | 正常 | 題目要求周天成被對手四角拉吊時的移動與勝率；程式追蹤的是對手自己在四角間的 hit_area 轉換，分析主體顛倒。 |
| 63 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 65 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 66 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 67 | 錯誤 | 正常 | 以 getpoint_player != opponent 判定殺球成功，會把 getpoint_player 為空的中間拍殺球一律算成成功，成功率與趨勢失真。 |
| 71 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 73 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 76 | 錯誤 | 正常 | 分析任一接殺防守後對手緊接的攻擊，而不是周天成跨步救球後下一次自己的攻擊；主體與時序皆不符合題意，且成功條件也會納入空值終結欄位。 |
| 79 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 80 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 82 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 83 | 錯誤 | 正常 | next_opponent_scored 實際寫成 next_getpoint_player == CHOU Tien Chen，將周天成得分誤標成對手得分，結論方向完全相反。 |
| 84 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 85 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 88 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 89 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 91 | 錯誤 | 正常 | 將對手在右後場出球且最後周天成贏得該回合的每一拍都標成對手失誤，未限制最後一拍與 lose_reason；右後場失誤率及主動得分率皆被錯誤重複計算。 |
| 93 | 錯誤 | 正常 | 題目指定對手在 18 分以上的關鍵分情境；程式只用 CHOU Tien Chen_score >= 18 篩選，分析到的是周天成自己的比分條件，母體不符題意。 |
| 95 | 正確 | 正常 | 符合題意與可接受範例邏輯 |
| 100 | 正確 | 正常 | 符合題意與可接受範例邏輯 |

## 判定說明

依 `example_new.ipynb` 的所有可接受範例與題意判定。題意未明確時，允許合理的分析條件與代理定義；不因圖表形式或實作細節不同判錯。
