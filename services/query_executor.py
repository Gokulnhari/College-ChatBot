"""
Query executor service.
Handles safe execution of structured queries against the DataFrame.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List

from config import settings
from utils import validator
from .type_converter import smart_type_match

class QueryExecutor:
    """Executes structured queries on DataFrame safely"""
    
    def __init__(self):
        self.df = settings.get_dataframe()
    
    def execute(self, structured_query: Dict[str, Any]) -> Any:
        """
        Execute a structured query on the DataFrame.
        
        Args:
            structured_query: Dictionary containing query specifications
            
        Returns:
            Query result (can be number, list of dicts, or None)
            
        Security:
            - Validates all operators against whitelist
            - Validates all columns exist
            - Validates all aggregation functions
            - No eval() or exec() used
        """
        try:
            filtered_df = self.df.copy()
            print(f"Initial DataFrame shape: {filtered_df.shape}")
            
            # Step 1: Apply filters
            filtered_df = self._apply_filters(filtered_df, structured_query.get("filters"))
            
            if filtered_df.empty:
                print("Filtered DataFrame is empty. Returning None.")
                return None
            
            query_type = structured_query.get("query_type", "aggregate")
            
            # Step 2: Execute based on query type
            if query_type == "list":
                return self._execute_list_query(filtered_df, structured_query)
            else:
                return self._execute_aggregate_query(filtered_df, structured_query)
                
        except Exception as e:
            return {"error": str(e)}
    
    def _apply_filters(
        self, 
        df: pd.DataFrame, 
        filters: Optional[List[Dict[str, Any]]]
    ) -> pd.DataFrame:
        """Apply filter conditions to DataFrame"""
        if not filters:
            return df
        
        for filter_condition in filters:
            col = filter_condition["column"]
            op = filter_condition["operator"]
            val = filter_condition["value"]
            
            # Security: Validate column exists
            if not validator.validate_column(col, self.df.columns.tolist()):
                raise ValueError(f"Invalid column: {col}")
            
            # Security: Validate operator
            if not validator.validate_operator(op):
                raise ValueError(f"Invalid operator: {op}")
            
            # Convert type to match column
            val = smart_type_match(self.df[col], val)
            
            # Apply filter (safe - no eval/exec)
            if op == "==":
                df = df[df[col] == val]
            elif op == "!=":
                df = df[df[col] != val]
            elif op == ">":
                df = df[df[col] > val]
            elif op == "<":
                df = df[df[col] < val]
            elif op == ">=":
                df = df[df[col] >= val]
            elif op == "<=":
                df = df[df[col] <= val]
        
        print(f"  Shape after filter: {df.shape}")
        
        return df
    
    def _execute_list_query(
        self, 
        df: pd.DataFrame, 
        query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute a list query (returns rows)"""
        select_columns = query.get("select_columns")
        
        # Validate and select columns
        if select_columns:
            print(f"  Selecting columns: {select_columns}")
            for col in select_columns:
                if not validator.validate_column(col, self.df.columns.tolist()):
                    raise ValueError(f"Invalid column: {col}")
            result_df = df[select_columns]
        else:
            result_df = df
        
        # Sort
        sort_spec = query.get("sort_by")
        if sort_spec:
            sort_col = sort_spec["column"]
            ascending = sort_spec.get("ascending", True)
            print(f"  Sorting by: {sort_col}, ascending: {ascending}")
            if sort_col in result_df.columns:
                result_df = result_df.sort_values(by=sort_col, ascending=ascending)
        
        # Handle "highest" or "lowest" queries to include all ties
        limit = query.get("limit")
        if sort_spec and limit is not None and limit >= 1: # Only if sort_by and limit are present
            if len(result_df) > 0: # Ensure there are results to process
                # Get the value at the limit boundary
                # E.g., if limit is 1, get the highest score. If limit is 5, get the 5th highest score.
                cutoff_index = min(limit - 1, len(result_df) - 1)
                cutoff_value = result_df.iloc[cutoff_index][sort_col]
                
                # Filter to include all rows that have value equal to or better than the cutoff
                if ascending: # For "lowest" queries (ascending order)
                    result_df = result_df[result_df[sort_col] <= cutoff_value]
                else: # For "highest" queries (descending order)
                    result_df = result_df[result_df[sort_col] >= cutoff_value]
        
        # If no sort_by, or no specific limit handling, apply limit directly (or re-apply if it was adjusted)
        elif limit:
            result_df = result_df.head(limit)
        
        print(f"  List query result DF head:\n{result_df.head()}")
        return result_df.to_dict(orient='records')
    
    def _execute_aggregate_query(
        self, 
        df: pd.DataFrame, 
        query: Dict[str, Any]
    ) -> Any:
        """Execute an aggregate query (returns statistics)"""
        group_by_cols = query.get("group_by")
        
        # Group if needed
        if group_by_cols:
            print(f"  Grouping by: {group_by_cols}")
            for col in group_by_cols:
                if not validator.validate_column(col, self.df.columns.tolist()):
                    raise ValueError(f"Invalid group_by column: {col}")
            grouped = df.groupby(group_by_cols)
        else:
            grouped = None
        
        # Apply aggregations
        aggregations = query.get("aggregations", [])
        if not aggregations:
            raise ValueError("No aggregations specified for aggregate query")
        
        results = {}
        
        for agg_spec in aggregations:
            func = agg_spec["function"]
            col = agg_spec["column"]
            alias = agg_spec.get("alias", f"{func}_{col}")
            print(f"  Applying aggregation: {func} on {col} as {alias}")
            
            # Security: Validate
            if not validator.validate_aggregation(func):
                raise ValueError(f"Invalid aggregation: {func}")
            if not validator.validate_column(col, self.df.columns.tolist()):
                raise ValueError(f"Invalid column: {col}")
            
            # Execute aggregation
            results[alias] = self._apply_aggregation(grouped or df, col, func, grouped is not None)
        
        # Combine results
        if grouped:
            result_df = pd.DataFrame(results).reset_index()
        else:
            result_df = pd.DataFrame([results])
        
        # Sort
        result_df = self._apply_sort(result_df, query.get("sort_by"))
        
        # Limit
        limit = query.get("limit")
        if limit:
            print(f"  Applying limit: {limit}")
            result_df = result_df.head(limit)
        
        print(f"  Aggregate query result DF:\n{result_df}")
        # Convert to output
        return self._format_result(result_df)
    
    def _apply_aggregation(
        self, 
        data, 
        column: str, 
        function: str, 
        is_grouped: bool
    ):
        """Apply aggregation function safely"""
        if is_grouped:
            # data is a GroupBy object
            if function == "count":
                return data[column].count()
            elif function == "sum":
                return data[column].sum()
            elif function == "mean":
                return data[column].mean()
            elif function == "median":
                return data[column].median()
            elif function == "max":
                return data[column].max()
            elif function == "min":
                return data[column].min()
            elif function == "std":
                return data[column].std()
            elif function == "var":
                return data[column].var()
        else:
            # data is a DataFrame
            if function == "count":
                return data[column].count()
            elif function == "sum":
                return data[column].sum()
            elif function == "mean":
                return data[column].mean()
            elif function == "median":
                return data[column].median()
            elif function == "max":
                return data[column].max()
            elif function == "min":
                return data[column].min()
            elif function == "std":
                return data[column].std()
            elif function == "var":
                return data[column].var()
    
    def _apply_sort(
        self, 
        df: pd.DataFrame, 
        sort_spec: Optional[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Apply sorting to DataFrame"""
        if not sort_spec:
            return df
        
        sort_col = sort_spec["column"]
        ascending = sort_spec.get("ascending", True)
        
        if sort_col in df.columns:
            return df.sort_values(by=sort_col, ascending=ascending)
        
        return df
    
    def _format_result(self, result_df: pd.DataFrame) -> Any:
        """Format result for API response"""
        # Single value result
        if len(result_df) == 1 and len(result_df.columns) == 1:
            val = result_df.iloc[0, 0]
            if pd.isna(val):
                return None
            return float(val) if isinstance(val, (np.floating, np.integer)) else val
        
        # Table result
        return result_df.to_dict(orient='records')

# Create singleton instance
query_executor = QueryExecutor()