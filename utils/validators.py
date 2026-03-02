"""
Security validators and whitelists.
These define what operations are allowed for security.
"""

class SecurityValidator:
    """Security validation for queries"""
    
    # Allowed comparison operators
    ALLOWED_OPERATORS = {"==", "!=", ">", "<", ">=", "<="}
    
    # Allowed aggregation functions
    ALLOWED_AGGREGATIONS = {"max", "min", "mean", "sum", "count", "median", "std", "var"}
    
    @classmethod
    def validate_operator(cls, operator: str) -> bool:
        """Check if operator is allowed"""
        return operator in cls.ALLOWED_OPERATORS
    
    @classmethod
    def validate_aggregation(cls, function: str) -> bool:
        """Check if aggregation function is allowed"""
        return function in cls.ALLOWED_AGGREGATIONS
    
    @classmethod
    def validate_column(cls, column: str, valid_columns: list) -> bool:
        """Check if column exists in dataset"""
        return column in valid_columns

# Create singleton instance
validator = SecurityValidator()