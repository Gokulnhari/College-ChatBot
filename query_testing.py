import pandas as pd

df= pd.read_csv("school_system_large.csv")

# Query to get marks of Meerasharma from Class 7 Section B 
students_8B = df[(df['Full_Name'] == 'Priya Sharma') & (df['Class'] == '8') & (df['Section'] == 'B')]

# To count them
print("Number of students in Class 8 Section B:", len(students_8B))