import pandas as pd
import numpy as np
from utils.data_loader import get_data_schema

def test_schema_formatting():
    # Create a dummy dataframe
    data = {
        'A': [1, 2, np.nan, 4, 5],
        'B': ['a', 'b', 'a', None, 'c'],
        'C': [1.1, 2.2, 3.3, 4.4, 5.5]
    }
    df = pd.DataFrame(data)
    
    print("Testing get_data_schema...")
    schema_output = get_data_schema(df)
    
    print("\n--- Output Start ---")
    print(schema_output)
    print("--- Output End ---\n")
    
    # Assertions
    if "RangeIndex" in schema_output and "Data columns" in schema_output:
         print("FAILED: df.info() output detected (should be removed).")
    else:
         print("PASSED: df.info() output successfully removed.")

    if "缺失值: 1 (20" in schema_output: # 1 missing out of 5 is 20%
         print("PASSED: Missing value count and percentage detected.")
    else:
         print("FAILED: Missing value percentage not found or incorrect.")

    if "數值範圍" in schema_output:
        print("PASSED: Numeric range detected.")
    else:
        print("FAILED: Numeric range missing.")

if __name__ == "__main__":
    test_schema_formatting()
