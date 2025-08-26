import pandas as pd
import json

# Load the Excel file
df = pd.read_excel(r"C:\Users\breadsp2\Desktop\olloma testing\sample_queries.xlsx")

# Convert DataFrame to JSON format
# orient='records' creates a list of dictionaries, where each dictionary represents a row
json_data = df.to_json(orient='records', indent=4)  # indent for pretty printing

# Write the JSON data to a file
output_json_file = "training_data.json"
with open(output_json_file, 'w') as f:
    f.write(json_data)

print(f"Excel data converted to JSON and saved to {output_json_file}")