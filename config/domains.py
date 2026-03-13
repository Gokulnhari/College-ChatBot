"""
Domain-specific configurations for different industries/use-cases.
Allows the chatbot to work with any domain by simply changing configuration.

To add a new domain:
1. Define domain config with entity_name, fields, example_queries
2. Add to AVAILABLE_DOMAINS
3. Set active domain in settings.py or via environment variable
"""
from typing import Dict, List, Any


class DomainConfig:
    """Configuration for a specific domain/industry"""

    def __init__(
        self,
        name: str,
        entity_name: str,
        entity_name_plural: str,
        csv_file_path: str,
        fields: List[Dict[str, Any]],
        example_queries: List[str],
        description: str = ""
    ):
        self.name = name
        self.entity_name = entity_name
        self.entity_name_plural = entity_name_plural
        self.csv_file_path = csv_file_path
        self.fields = fields
        self.example_queries = example_queries
        self.description = description

    @property
    def field_names(self) -> List[str]:
        """Get list of all field names"""
        return [f["name"] for f in self.fields]

    @property
    def numeric_fields(self) -> List[str]:
        """Get list of numeric field names"""
        return [f["name"] for f in self.fields if f["type"] in ["int", "float"]]

    @property
    def categorical_fields(self) -> List[str]:
        """Get list of categorical field names"""
        return [f["name"] for f in self.fields if f["type"] == "category"]

    @property
    def text_fields(self) -> List[str]:
        """Get list of text field names"""
        return [f["name"] for f in self.fields if f["type"] == "string"]

    def get_field_description(self, field_name: str) -> str:
        """Get human-readable description for a field"""
        for field in self.fields:
            if field["name"] == field_name:
                return field.get("description", field_name)
        return field_name


# ============================================================================
# EDUCATION DOMAIN (Original)
# ============================================================================

EDUCATION_DOMAIN = DomainConfig(
    name="education",
    entity_name="student",
    entity_name_plural="students",
    csv_file_path="school_system_with_emails.csv",
    description="Student academic records and performance tracking",
    fields=[
    {"name": "Student_ID", "type": "string", "description": "Unique student identifier"},
    {"name": "Full_Name", "type": "string", "description": "Student's full name"},
    {"name": "Gender", "type": "category", "description": "Student's gender"},
    {"name": "Class", "type": "int", "description": "Class/Grade level"},
    {"name": "Section", "type": "category", "description": "Class section (A, B, C, etc.)"},
    {"name": "Math_Marks", "type": "int", "description": "Mathematics test score"},
    {"name": "Science_Marks", "type": "int", "description": "Science test score"},
    {"name": "English_Marks", "type": "int", "description": "English test score"},
    {"name": "Social_Marks", "type": "int", "description": "Social Studies test score"},
    {"name": "Computer_Marks", "type": "int", "description": "Computer Science test score"},
    {"name": "Attendance_Percentage", "type": "float", "description": "Attendance percentage"},
    {"name": "Fee_Paid", "type": "category", "description": "Fee payment status (Yes/No)"},

    {"name": "Email", "type": "string", "description": "Student email address"},
    {"name": "Parent_Email", "type": "string", "description": "Parent email address"},
],
    example_queries=[
    "Show me top 5 students in class 10",
    "What is the average Math marks for Section A?",
    "List students with attendance below 75%",
    "Who has the highest total marks?",
    "Compare marks of John Doe and Jane Smith",
    "Send email to all class 10 students about exam schedule",
    "Email students with attendance below 75%",
    "Notify parents of class 8 section B about meeting",
    ]
)


# ============================================================================
# BANKING DOMAIN
# ============================================================================

BANKING_DOMAIN = DomainConfig(
    name="banking",
    entity_name="customer",
    entity_name_plural="customers",
    csv_file_path="banking_customers.csv",
    description="Banking customer accounts and transactions",
    fields=[
        {"name": "Customer_ID", "type": "string", "description": "Unique customer identifier"},
        {"name": "Full_Name", "type": "string", "description": "Customer's full name"},
        {"name": "Account_Type", "type": "category", "description": "Account type (Savings/Current/Fixed)"},
        {"name": "Account_Number", "type": "string", "description": "Bank account number"},
        {"name": "Balance", "type": "float", "description": "Current account balance"},
        {"name": "Credit_Score", "type": "int", "description": "Credit score (300-850)"},
        {"name": "Branch", "type": "category", "description": "Home branch location"},
        {"name": "Account_Status", "type": "category", "description": "Account status (Active/Inactive/Frozen)"},
        {"name": "Monthly_Transactions", "type": "int", "description": "Number of monthly transactions"},
        {"name": "Last_Transaction_Date", "type": "string", "description": "Date of last transaction"},
        {"name": "Loan_Amount", "type": "float", "description": "Outstanding loan amount"},
        {"name": "KYC_Status", "type": "category", "description": "KYC verification status (Verified/Pending)"},
    ],
    example_queries=[
        "Show customers with balance above $50,000",
        "List all accounts with pending KYC",
        "What is the average credit score by branch?",
        "Find customers with loans over $100,000",
        "Show top 10 customers by account balance",
    ]
)


# ============================================================================
# HEALTHCARE DOMAIN
# ============================================================================

HEALTHCARE_DOMAIN = DomainConfig(
    name="healthcare",
    entity_name="patient",
    entity_name_plural="patients",
    csv_file_path="healthcare_patients.csv",
    description="Patient medical records and appointments",
    fields=[
        {"name": "Patient_ID", "type": "string", "description": "Unique patient identifier"},
        {"name": "Full_Name", "type": "string", "description": "Patient's full name"},
        {"name": "Age", "type": "int", "description": "Patient age in years"},
        {"name": "Gender", "type": "category", "description": "Patient gender"},
        {"name": "Blood_Type", "type": "category", "description": "Blood type (A+, B+, O-, etc.)"},
        {"name": "Department", "type": "category", "description": "Primary department (Cardiology, Orthopedics, etc.)"},
        {"name": "Doctor_Assigned", "type": "string", "description": "Assigned doctor name"},
        {"name": "Admission_Date", "type": "string", "description": "Last admission date"},
        {"name": "Diagnosis", "type": "string", "description": "Primary diagnosis"},
        {"name": "Treatment_Status", "type": "category", "description": "Treatment status (Active/Completed/Ongoing)"},
        {"name": "Insurance_Provider", "type": "category", "description": "Insurance company name"},
        {"name": "Outstanding_Bills", "type": "float", "description": "Pending payment amount"},
    ],
    example_queries=[
        "Show all patients in the Cardiology department",
        "List patients with outstanding bills above $5,000",
        "What is the average age of patients by department?",
        "Find all patients with blood type O-",
        "Show patients under Dr. Smith's care",
    ]
)


# ============================================================================
# RETAIL/ECOMMERCE DOMAIN
# ============================================================================

RETAIL_DOMAIN = DomainConfig(
    name="retail",
    entity_name="customer",
    entity_name_plural="customers",
    csv_file_path="retail_customers.csv",
    description="E-commerce customer orders and behavior",
    fields=[
        {"name": "Customer_ID", "type": "string", "description": "Unique customer identifier"},
        {"name": "Full_Name", "type": "string", "description": "Customer's full name"},
        {"name": "Email", "type": "string", "description": "Customer email address"},
        {"name": "Total_Orders", "type": "int", "description": "Total number of orders placed"},
        {"name": "Total_Spent", "type": "float", "description": "Total amount spent"},
        {"name": "Average_Order_Value", "type": "float", "description": "Average order value"},
        {"name": "Customer_Segment", "type": "category", "description": "Customer segment (VIP/Regular/New)"},
        {"name": "Last_Purchase_Date", "type": "string", "description": "Date of last purchase"},
        {"name": "Preferred_Category", "type": "category", "description": "Most purchased category"},
        {"name": "Loyalty_Points", "type": "int", "description": "Accumulated loyalty points"},
        {"name": "Returns_Count", "type": "int", "description": "Number of returned orders"},
        {"name": "Subscription_Status", "type": "category", "description": "Subscription status (Active/Inactive)"},
    ],
    example_queries=[
        "Show VIP customers with over $10,000 spent",
        "List customers who haven't purchased in 6 months",
        "What is the average order value by customer segment?",
        "Find customers with high return rates",
        "Show top 10 customers by loyalty points",
    ]
)


# ============================================================================
# HR/EMPLOYEE DOMAIN
# ============================================================================

HR_DOMAIN = DomainConfig(
    name="hr",
    entity_name="employee",
    entity_name_plural="employees",
    csv_file_path="hr_employees.csv",
    description="Human resources employee records",
    fields=[
        {"name": "Employee_ID", "type": "string", "description": "Unique employee identifier"},
        {"name": "Full_Name", "type": "string", "description": "Employee's full name"},
        {"name": "Department", "type": "category", "description": "Department name"},
        {"name": "Position", "type": "string", "description": "Job title/position"},
        {"name": "Salary", "type": "float", "description": "Annual salary"},
        {"name": "Hire_Date", "type": "string", "description": "Date of joining"},
        {"name": "Performance_Rating", "type": "float", "description": "Performance rating (1-5)"},
        {"name": "Manager", "type": "string", "description": "Direct manager name"},
        {"name": "Location", "type": "category", "description": "Office location"},
        {"name": "Employment_Type", "type": "category", "description": "Employment type (Full-time/Part-time/Contract)"},
        {"name": "Years_of_Experience", "type": "int", "description": "Years of work experience"},
        {"name": "Training_Hours", "type": "int", "description": "Hours of training completed"},
    ],
    example_queries=[
        "Show employees in the Engineering department",
        "List employees with performance rating above 4.5",
        "What is the average salary by department?",
        "Find employees hired in the last 6 months",
        "Show top performers by department",
    ]
)


# ============================================================================
# INVENTORY/WAREHOUSE DOMAIN
# ============================================================================

INVENTORY_DOMAIN = DomainConfig(
    name="inventory",
    entity_name="product",
    entity_name_plural="products",
    csv_file_path="inventory_products.csv",
    description="Warehouse inventory and stock management",
    fields=[
        {"name": "Product_ID", "type": "string", "description": "Unique product identifier"},
        {"name": "Product_Name", "type": "string", "description": "Product name"},
        {"name": "Category", "type": "category", "description": "Product category"},
        {"name": "SKU", "type": "string", "description": "Stock keeping unit code"},
        {"name": "Quantity_In_Stock", "type": "int", "description": "Current stock quantity"},
        {"name": "Reorder_Level", "type": "int", "description": "Minimum stock level for reorder"},
        {"name": "Unit_Price", "type": "float", "description": "Price per unit"},
        {"name": "Supplier", "type": "category", "description": "Supplier name"},
        {"name": "Warehouse_Location", "type": "category", "description": "Warehouse location"},
        {"name": "Last_Restocked_Date", "type": "string", "description": "Last restock date"},
        {"name": "Expiry_Date", "type": "string", "description": "Product expiry date (if applicable)"},
        {"name": "Status", "type": "category", "description": "Stock status (In Stock/Low Stock/Out of Stock)"},
    ],
    example_queries=[
        "Show products with stock below reorder level",
        "List all out of stock items",
        "What is the total inventory value by category?",
        "Find products expiring in the next 30 days",
        "Show top 10 products by quantity in stock",
    ]
)


# ============================================================================
# REGISTRY - All Available Domains
# ============================================================================

AVAILABLE_DOMAINS: Dict[str, DomainConfig] = {
    "education": EDUCATION_DOMAIN,
    "banking": BANKING_DOMAIN,
    "healthcare": HEALTHCARE_DOMAIN,
    "retail": RETAIL_DOMAIN,
    "hr": HR_DOMAIN,
    "inventory": INVENTORY_DOMAIN,
}


def get_domain(domain_name: str) -> DomainConfig:
    """
    Get domain configuration by name.

    Args:
        domain_name: Name of the domain (education, banking, healthcare, etc.)

    Returns:
        DomainConfig instance

    Raises:
        ValueError: If domain not found
    """
    if domain_name not in AVAILABLE_DOMAINS:
        available = ", ".join(AVAILABLE_DOMAINS.keys())
        raise ValueError(
            f"Domain '{domain_name}' not found. Available domains: {available}"
        )
    return AVAILABLE_DOMAINS[domain_name]


def list_domains() -> List[str]:
    """Get list of all available domain names"""
    return list(AVAILABLE_DOMAINS.keys())
