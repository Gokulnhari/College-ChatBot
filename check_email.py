
import pandas as pd
from config import settings

df = settings.get_dataframe()
if df is None:
    # load directly
    df = pd.read_csv(r'C:\Users\gokul\Downloads\Telegram Desktop\Analystor\Final_Project\school_chatbot_with_llm-main\school_system_with_emails.csv')  # replace with your CSV path

row = df[df['Student_ID'] == 5001]
print(row[['Student_ID', 'Full_Name', 'Email', 'Parent_Email']].to_string())

