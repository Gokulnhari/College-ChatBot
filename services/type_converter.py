"""
Type conversion utilities.
Handles matching filter values to DataFrame column types.
"""
import pandas as pd
from typing import Any

def smart_type_match(column_series: pd.Series, filter_value: Any) -> Any:
    """
    Convert filter_value to match the column's dtype.
    
    This prevents type mismatch errors where a string "10" 
    doesn't match an integer 10 in the DataFrame.
    
    Args:
        column_series: The pandas Series (column) to match against
        filter_value: The value to convert
        
    Returns:
        Converted value matching the column's type
        
    Example:
        >>> col = df['Class']  # dtype: int64
        >>> smart_type_match(col, "10")  # Returns: 10 (int)
        >>> 
        >>> col = df['Gender']  # dtype: object (string)
        >>> smart_type_match(col, "Male")  # Returns: "Male" (str)
    """
    column_dtype = column_series.dtype
    
    # If column is numeric (int or float)
    if pd.api.types.is_numeric_dtype(column_dtype):
        try:
            if isinstance(filter_value, str):
                # Check if it's a float or int
                if '.' in filter_value:
                    return float(filter_value)
                else:
                    return int(filter_value)
            return filter_value
        except (ValueError, TypeError):
            # If conversion fails, return as-is
            return filter_value
    else:
        # If column is string/object, convert to string
        return str(filter_value)