import pandas as pd
import io

def generate_excel_bytes(schedule_df: pd.DataFrame) -> bytes:
    """
    Takes the master schedule DataFrame and writes a multi-sheet Excel file.
    Returns raw bytes ready for a Streamlit download button.
    """
    # Create an in-memory buffer
    buffer = io.BytesIO()
    
    # Needs openpyxl installed
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        
        # 1. Master Sheet
        # Extract PGY integers to sort accurately (Seniors first, so largest PGY -> smallest)
        # Assuming format "PGY-1", "PGY-2" etc.
        if 'Year' in schedule_df.columns:
            # Create a temporary sort key
            schedule_df['_pgy_num'] = schedule_df['Year'].apply(lambda x: int(x.split('-')[1]) if '-' in x else 0)
            master_sorted = schedule_df.sort_values(by='_pgy_num', ascending=False).drop(columns=['_pgy_num'])
        else:
            master_sorted = schedule_df

        master_sorted.to_excel(writer, sheet_name='Master Schedule', index=False)

        # 2. Individual Resident Sheets
        months_cols = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        
        for idx, row in master_sorted.iterrows():
            res_name = row['Resident']
            
            # Create a localized dataframe for just this resident transposed
            resident_data = []
            for col in master_sorted.columns:
                if col in months_cols: # Only map the month columns
                    resident_data.append({"Month": col, "Assigned Rotation": row[col]})
                    
            res_df = pd.DataFrame(resident_data)
            
            # Write to its own sheet. Openpyxl limits sheet names to 31 chars safely.
            safe_sheet_name = str(res_name)[:31]
            # Replace invalid sheet name chars
            invalid_chars = ['*', ':', '?', '/', '\\', '[', ']']
            for char in invalid_chars:
                safe_sheet_name = safe_sheet_name.replace(char, '')
                
            res_df.to_excel(writer, sheet_name=safe_sheet_name, index=False)

    return buffer.getvalue()
