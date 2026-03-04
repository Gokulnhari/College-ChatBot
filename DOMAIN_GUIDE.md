## Domain Configuration Guide

Your chatbot is now **domain-agnostic** and can work with any industry or use-case by simply changing the domain configuration.

## Quick Start

### 1. Switch Domains Interactively

```bash
python domain_switcher.py
```

This will show you all available domains and let you choose one.

### 2. Switch Domains via Command Line

```bash
# Switch to banking domain
python domain_switcher.py --domain banking

# Switch to healthcare domain
python domain_switcher.py --domain healthcare

# List all available domains
python domain_switcher.py --list
```

### 3. Set Domain via Environment Variable

```bash
# Temporary (current session)
export DOMAIN=banking
python main.py

# Permanent (add to .env file)
echo "DOMAIN=banking" >> .env
```

---

## Available Domains

### 1. Education (Default)
- **Entity**: Students
- **CSV**: `school_system_large.csv`
- **Use Case**: Student records, grades, attendance
- **Example**: "Show top 5 students in class 10"

### 2. Banking
- **Entity**: Customers
- **CSV**: `banking_customers.csv`
- **Use Case**: Bank accounts, balances, transactions
- **Example**: "Show customers with balance above $50,000"

### 3. Healthcare
- **Entity**: Patients
- **CSV**: `healthcare_patients.csv` *(you need to create this)*
- **Use Case**: Patient records, appointments, treatments
- **Example**: "List patients in the Cardiology department"

### 4. Retail/E-Commerce
- **Entity**: Customers
- **CSV**: `retail_customers.csv` *(you need to create this)*
- **Use Case**: Customer orders, loyalty, purchases
- **Example**: "Show VIP customers with over $10,000 spent"

### 5. HR/Employee Management
- **Entity**: Employees
- **CSV**: `hr_employees.csv` *(you need to create this)*
- **Use Case**: Employee records, performance, salaries
- **Example**: "Show employees in Engineering department"

### 6. Inventory/Warehouse
- **Entity**: Products
- **CSV**: `inventory_products.csv` *(you need to create this)*
- **Use Case**: Stock management, inventory tracking
- **Example**: "Show products with stock below reorder level"

---

## Creating a New Domain

### Step 1: Define Domain Configuration

Edit `config/domains.py` and add your domain:

```python
CUSTOM_DOMAIN = DomainConfig(
    name="custom",
    entity_name="order",                    # Singular
    entity_name_plural="orders",            # Plural
    csv_file_path="custom_orders.csv",     # Your CSV file
    description="Custom order management system",
    fields=[
        {"name": "Order_ID", "type": "string", "description": "Unique order ID"},
        {"name": "Customer_Name", "type": "string", "description": "Customer name"},
        {"name": "Order_Total", "type": "float", "description": "Total order amount"},
        {"name": "Status", "type": "category", "description": "Order status"},
        # Add more fields...
    ],
    example_queries=[
        "Show orders above $1000",
        "List pending orders",
        "What is the average order value?",
    ]
)

# Add to registry
AVAILABLE_DOMAINS["custom"] = CUSTOM_DOMAIN
```

### Step 2: Create CSV File

Create a CSV file matching your field names:

```csv
Order_ID,Customer_Name,Order_Total,Status
ORD001,John Doe,1250.00,Completed
ORD002,Jane Smith,850.50,Pending
ORD003,Bob Johnson,2100.00,Shipped
```

Save as `custom_orders.csv` in the project root.

### Step 3: Switch to Your Domain

```bash
python domain_switcher.py --domain custom
```

That's it! The system will now:
- Use your CSV file
- Generate appropriate prompts for your domain
- Understand queries about your entity type

---

## How It Works

### Domain-Aware Components

#### 1. **Prompts** (Automatic)
All prompts are automatically generated based on your domain:

```python
# Classification
"If the user question is related to {entity_name_plural} data..."

# Query Planning
"Convert questions about {entity_name_plural} into structured queries..."

# Response Generation
"You are a helpful assistant for a {description} system..."
```

#### 2. **CSV Mode** (Automatic)
The system automatically:
- Loads your CSV file
- Knows your field names and types
- Generates appropriate pandas queries
- Formats responses using your entity names

#### 3. **RAG Mode** (Automatic)
When users upload documents:
- Prompts mention your domain context
- Responses are tailored to your entity type
- Citations reference your domain terminology

---

## Advanced: Domain-Specific Customization

### Custom Validation Rules

Add validation in `utils/validators.py`:

```python
from config import settings

def validate_query(query):
    domain = settings.get_domain()

    if domain.name == "banking":
        # Banking-specific validation
        if "balance" in query and query["value"] < 0:
            raise ValueError("Balance cannot be negative")

    elif domain.name == "healthcare":
        # Healthcare-specific validation
        # HIPAA compliance checks, etc.
        pass
```

### Custom Query Transformations

Override in `services/query_executor.py`:

```python
from config import settings

def execute(query):
    domain = settings.get_domain()

    # Domain-specific preprocessing
    if domain.name == "retail":
        # Calculate customer lifetime value
        if query.get("aggregation", {}).get("function") == "lifetime_value":
            # Custom calculation
            pass

    # Standard execution
    return standard_execute(query)
```

### Custom UI Elements

Add domain-specific widgets in `streamlit_app.py`:

```python
from config import settings

domain = settings.get_domain()

if domain.name == "banking":
    # Banking-specific filters
    st.sidebar.selectbox("Branch", ["Downtown", "Uptown", "Midtown"])

elif domain.name == "healthcare":
    # Healthcare-specific filters
    st.sidebar.selectbox("Department", ["Cardiology", "Orthopedics"])
```

---

## Examples by Domain

### Banking Queries
```
"Show customers with credit score above 700"
"List all frozen accounts"
"What is the average balance by branch?"
"Find customers with pending KYC"
"Show top 10 customers by account balance"
```

### Healthcare Queries
```
"List all patients in Cardiology"
"Show patients with outstanding bills above $5000"
"What is the average age by department?"
"Find patients with blood type O-"
"Show all patients under Dr. Smith"
```

### Retail Queries
```
"Show VIP customers"
"List customers who haven't purchased in 6 months"
"What is the average order value by segment?"
"Find customers with high return rates"
"Show top 10 customers by loyalty points"
```

### HR Queries
```
"Show employees in Engineering"
"List employees with rating above 4.5"
"What is the average salary by department?"
"Find employees hired in last 6 months"
"Show top performers by department"
```

---

## Multi-Tenant Setup (Advanced)

For enterprise deployments with multiple domains:

### Option 1: Environment Variable per Instance

```bash
# Terminal 1 - Banking instance
export DOMAIN=banking
export API_PORT=8001
python main.py

# Terminal 2 - Healthcare instance
export DOMAIN=healthcare
export API_PORT=8002
python main.py
```

### Option 2: Runtime Domain Selection

Add API endpoint in `routes/api.py`:

```python
@router.post("/set-domain")
async def set_domain(domain_name: str, user: User = Depends(auth)):
    # Check permissions
    if not user.can_switch_domains():
        raise HTTPException(403)

    # Switch domain for this session
    settings.set_domain(domain_name)
    return {"domain": domain_name, "status": "switched"}
```

### Option 3: Domain Selector in UI

Add to `streamlit_app.py`:

```python
from config.domains import list_domains
from config import settings

domain_choice = st.sidebar.selectbox(
    "Select Domain",
    list_domains(),
    index=list_domains().index(settings.ACTIVE_DOMAIN)
)

if domain_choice != settings.ACTIVE_DOMAIN:
    settings.set_domain(domain_choice)
    st.rerun()
```

---

## Troubleshooting

### Domain Switch Not Working

**Issue**: Domain switch doesn't persist after restart

**Solution**: Set environment variable or add to `.env`:
```bash
echo "DOMAIN=banking" >> .env
```

### CSV File Not Found

**Issue**: `FileNotFoundError: banking_customers.csv`

**Solution**:
1. Check file exists in project root
2. Verify filename matches domain config
3. Create file using provided template

### Wrong Fields in Queries

**Issue**: LLM uses old field names after domain switch

**Solution**:
1. Restart backend: `python main.py`
2. Clear chat history in Streamlit
3. Verify domain config has correct fields

### Prompts Still Mention Old Domain

**Issue**: Prompts still say "students" after switching to banking

**Solution**:
1. Ensure you're importing from `prompts.templates`
2. Check `services/llm_service.py` uses template functions
3. Restart both frontend and backend

---

## Best Practices

### 1. Naming Conventions
- Domain names: lowercase, no spaces (`banking`, not `Banking System`)
- Entity names: singular (`customer`, not `customers`)
- CSV files: `{domain_name}_{entities}.csv`

### 2. Field Design
- Use consistent naming: `Field_Name` (PascalCase with underscores)
- Always include an ID field
- Include name/identifier field for entity
- Add at least one numeric field for aggregations
- Add at least one categorical field for grouping

### 3. Field Types
- `string`: Text fields, IDs, names
- `int`: Whole numbers, counts
- `float`: Decimals, money, percentages
- `category`: Limited set of values (status, type, etc.)

### 4. CSV Requirements
- First row = headers (must match field names exactly)
- No empty headers
- Consistent data types per column
- Use UTF-8 encoding
- Avoid special characters in headers

### 5. Example Queries
- Provide 3-5 representative queries
- Cover different query types (filter, aggregate, sort)
- Use actual field names from your domain
- Make them realistic and useful

---

## Migration from Hardcoded System

If migrating from the old hardcoded student system:

### Before (Hardcoded)
```python
# prompts/__init__.py
QUERY_PLANNER_PROMPT = """
Convert questions about students into queries...
Available fields: Student_ID, Full_Name, Math_Marks...
"""
```

### After (Domain-Agnostic)
```python
# Automatic based on domain
from prompts.templates import get_query_planner_prompt
from config import settings

prompt = get_query_planner_prompt(settings.get_domain())
# Now works for students, customers, patients, etc.
```

---

## Support

For questions or issues:
1. Run `python domain_switcher.py --list` to verify domain config
2. Check CSV file exists and matches field names
3. Review `config/domains.py` for your domain definition
4. See main README.md for general troubleshooting

---

**Last Updated**: March 4, 2026
