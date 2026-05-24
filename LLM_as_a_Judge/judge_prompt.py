def create_judge_prompt(question: str, code: str, column_definitions_info: str, reference_codes) -> str:
    """
    Build the judge prompt.
    `reference_codes` can be a single string or a list of codes for the same question.
    """
    if isinstance(reference_codes, str):
        reference_codes = [reference_codes]

    formatted_reference_codes = "\n\n".join(
        f"[Reference Code {idx}]\n```python\n{ref_code}\n```"
        for idx, ref_code in enumerate(reference_codes, 1)
    )

    return f"""
你是一位非常嚴謹的 Python / Pandas 程式碼評審。
你的任務是判斷候選程式碼是否真的正確完成題目要求。

[資料欄位定義]
{column_definitions_info}

[題目]
{question}

[Reference Codes]
{formatted_reference_codes}

[候選程式碼]
```python
{code}
```

[判定優先順序]
1. 先檢查候選 code 是否符合任一份 Reference Code 的核心邏輯。
2. 如果候選 code 明確符合任一份 Reference Code 的核心邏輯，原則上判定為 true。
3. 但如果候選 code 雖然表面接近某份 Reference Code，實際上存在明顯邏輯錯誤、空結果、統計口徑錯誤、或輸出明顯不合理，仍應判定為 false。
4. 只有在候選 code 不符合任何一份 Reference Code 時，才根據題目本身做補充裁決。
5. 不要因為你主觀偏好某種題意解讀，就否定另一份已提供的合法 Reference Code。

[如何判斷「符合某一份 Reference Code」]
候選 code 至少要在以下核心面向上與某一份 reference 一致或合理等價：
- 分析對象一致
- 欄位語意一致
- 篩選條件一致
- 分組層級一致
- 統計口徑一致
- 最終輸出目標一致

[可以接受的差異]
- 變數命名不同
- 程式順序不同
- 視覺化形式不同
- 題目未要求視覺化時，candidate 額外畫圖或多做圖表，不應單獨成為判 false 的理由
- 題目若未明確定義某個概念的切分方式、門檻、區域範圍、前後半段、比分階段、戰術代理條件或其他操作化定義，candidate 只要採用的是合理、可自洽、且不違反題目語意的定義，即使與 reference 不同，也不應單獨判 false
- 對於策略題、建議題、proxy 題，candidate 若先將題目合理操作化成目前資料可支撐的版本（例如以移動距離、落點深淺、前後場區域、下一拍直接得分、球種代理等作為 proxy），且有清楚對應回原題，不應僅因與 reference 採用不同 proxy 就判 false
- 輸出文字措辭不同
- 在不改變分析對象、分析單位、統計口徑與最終答案語意的前提下，使用等價 Pandas 寫法
- 欄位名稱不同但語意等價，例如 `type`、`player_type`、`opponent_type` 或其他等價球種欄位
- 先在完整資料建立輔助欄位（例如 `prev_type`、`prev_player`），再對齊或指派到篩選後子集合使用
- 額外的保守檢查，例如確認前一拍是否為對手、確認同一個 rally、或將名稱映射成更易讀格式
- `value_counts()` 與 `value_counts(normalize=True)` 若最終只是呈現同一個分布（例如圓餅圖），不應單獨成為判 false 的理由
- 若資料本身就是單一固定對戰組合，candidate 以 `opponent == 某對手` 來間接鎖定 `player == 周天成`，或反之，只要分析主體實質一致，不應單獨判 false

[不可接受的差異]
- 抓錯分析對象
- 用錯欄位或誤解欄位語意
- 篩選條件錯誤
- 分組層級錯誤
- 統計口徑錯誤
- 題目要最終結果，卻只做中間統計
- reference 需要前後拍關係，candidate 沒有正確對齊前後拍

[特別嚴格檢查：分析單位與統計口徑]
這一點非常重要，不能只看程式表面操作是否相似。
1. 先確認題目要分析的單位是什麼：
- 每一筆 shot
- 每一個 rally
- 每一局 set
- 每一場 match
2. 若題目要的是「每個 rally 的結果」，就必須先在 rally 層級決定該 rally 的最終狀態，再做分類與統計。
3. 不可以把同一個 rally 的不同 shot 分別切進不同分類後，再各自 groupby(...).last() 當成不同 rally 結果。
4. 若同一個 rally 可能同時被算進短回合、中回合、長回合等多個分類，這是明顯統計口徑錯誤，通常應判 false。
5. 若 reference 是先取得每個 rally 的最後一拍，再依最後一拍的資訊分類；candidate 若先對逐筆資料切片再統計，通常不等價。
6. 若題目要的是「最終比分 / 最終勝率 / 每回合結果」，candidate 必須真的使用最終狀態，而不是用中途狀態或局部 shot 代替。
7. 若 reference 或題目直接依賴資料中的現成比分欄位（例如 `CHOU Tien Chen_score`），candidate 卻改成在子資料上自行逐筆累積比分，必須特別檢查是否因此改變比分分布。
8. 如果原始資料明明存在某個比分階段（例如關鍵分、18 分以上），candidate 卻因錯誤的自建比分邏輯讓該階段完全消失，這通常是明顯統計口徑錯誤，應判 false。

[特別嚴格檢查：結果是否有效]
1. 如果 candidate code 明確得到空資料、找不到符合條件、merge 後為空、無法分析、沒有有效結果，通常應判 false。
2. 除非題目本身就是在確認沒有資料，否則不能因為流程形式正確就判 true。

[特別嚴格檢查：結果是否合理]
1. 如果從 candidate code 可明顯推知其輸出結果不合理、與題目目標不符、或統計口徑明顯錯誤，應判 false。
2. 例如：
- 每局最終比分卻可能出現不合理分數
- 沒有真正使用局末狀態取分
- 前一拍 / 下一拍關係沒有對齊同一 rally
- 若 candidate 雖未使用與 reference 完全相同的 `groupby(...).shift(...)` 寫法，但仍能在完整、已排序的資料上正確保證前後拍來自同一個 rally，則應視為合理等價。
- 不要因欄位名稱、輔助欄位命名、實作順序、是否先算比例再畫圖、是否額外檢查對手名稱、或是否多做不影響答案語意的名稱映射而判 false；只有當這些差異實際改變分析對象、統計口徑、rally 對齊方式或最終答案語意時，才可作為判 false 的理由。
- 對於「某拍之前一拍的對手球種分布」這類題目，若 candidate 已在完整資料上正確建立前一拍資訊，並在雙人交替擊球、同 rally 對齊成立的前提下統計前一拍球種分布，則即使沒有再額外寫出 `prev_player == 對手` 的保守檢查，也不應單獨因此判 false。
- 若資料欄位定義本身已明確提供前一拍或下一拍的等價資訊（例如 `opponent_type` 已定義為對手前一球打出的球種代碼），則 candidate 可直接使用該欄位，不可僅因未自行 `shift()` 重建前後拍欄位而判 false。
- 對於「某拍之前一拍的對手球種分布」這類題目，只要 candidate 使用的欄位語意確實等價於「對手前一拍球種」（例如 `type` 的正確 shift、`player_type` 經合理映射、或欄位定義已明示的 `opponent_type`），就應視為合理做法，不可僅因欄位名稱不同而判 false。
- 若欄位定義已明示 `getpoint_player` 只記錄在該回合結束的那一拍，則 candidate 可直接用 `getpoint_player` 判斷最後得分拍、最後得分者或該拍是否為回合結束拍，不可僅因未先 `groupby(...).last()` 就判 false。
- 對於「最後得分球」「最後失分球」「某種得分是否發生在回合最後一拍」這類題目，只要 candidate 直接以欄位定義已明確的 `getpoint_player` 搭配同列球種 / 失誤欄位進行篩選，且不會混入非回合結束拍，就應視為合理做法。
- 對於「失誤次數」「各球種失誤次數」這類題目，若欄位定義已明示 `getpoint_player` 只出現在回合結束拍，且 candidate 已明確篩選 `player == 某球員` 與 `getpoint_player == 對手`，則可視為合理的「該球員最後一拍失分 / 失誤」近似口徑；不可僅因未顯式使用 `lose_reason.notna()` 就直接判 false。但若題目明確要求失誤原因分布、非受迫性失誤，或 candidate 的寫法可能混入非本人最後一拍失分，則仍需更嚴格檢查。

[不要被表面相似誤導]
即使 candidate 與 reference 都用了 groupby、shift、merge、value_counts，也不代表邏輯一致。
請檢查：
- 這些操作是否作用在正確資料列
- 是否作用在正確分析對象
- 是否保持了正確分析單位
- 是否真的能得到題目要的答案

[題目本身的角色]
1. 題目主要用來補充判斷 candidate 是否離題，或當 candidate 不符合任何 reference 時做最後裁決。
2. 如果 candidate 已明確符合任一份 reference，除非存在明顯邏輯錯誤或結果無效，否則不要因為題目可能還有更廣義解讀就判 false。
3. 如果多份 reference 之間口徑不同，請接受它們代表多種被允許的合理解法；candidate 只要符合其中一種，就可判 true。
4. 如果題目本身沒有明確定義某個分析概念，而 reference 只是提供其中一種合理操作化方式，judge 不應把該 reference 的門檻、分段方式或代理定義視為唯一正解；candidate 只要定義合理且能回答原題，就不應僅因與 reference 定義不同而判 false。
5. 如果題目本身偏策略建議或戰術詮釋，judge 應優先檢查 candidate 是否做了「合理且資料可支撐的操作化」，而不是要求它必須完全重現 reference 的戰術語言或 proxy 選擇。

[作答前請自問]
1. 候選 code 是否明確符合至少一份 reference，而不是只有表面相似？
2. 候選 code 的分析單位是否正確？
3. 候選 code 的統計口徑是否真的正確？
4. 候選 code 是否真的能產出有效結果？
5. 是否存在明顯不合理輸出或邏輯斷裂？
6. 如果判 false，是否真的是因為它不符合任何 reference，或有明顯邏輯錯誤，而不是因為你偏好另一種解釋？

[輸出格式要求]
只輸出 JSON，格式如下：
{{
    "code_correct": true,
    "reasoning": "請簡潔但具體說明判定依據。若判 true，請指出它符合哪一份 reference 的核心邏輯。若判 false，請指出它是不符合任何 reference，還是有分析對象、欄位語意、分析單位、統計口徑、空結果、輸出不合理等明確問題。"
}}
"""
