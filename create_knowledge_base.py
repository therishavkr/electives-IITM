import pandas as pd
import re
import io

# --- Prerequisite Data (Transcribed from your image for accuracy) ---
prerequisite_data = """
CourseNo,Prerequisite
AM1100,
AS2010,
AS2030,
AS2040,
AS2050,
AS2070,AS2010
AS2080,AM1100
# ... (and so on for all other prerequisites)
CS3500,CS2600;CS2700
"""

def create_knowledge_base():
    """
    Final, all-in-one script to create the clean, definitive knowledge base
    for the AI chatbot.
    """
    try:
        # 1. Load source files from your specific Google Drive paths
        base_path = ''
        sem_wise_df = pd.read_csv(base_path + 'sem_wise_details.csv')
        slotwise_df = pd.read_csv(base_path + 'slotwise_details_cleaned.csv')
        course_type_df = pd.read_csv(base_path + 'course_type.csv')
        
        print("✅ Step 1: Loaded all source CSV files from Drive.")

        # 2. Standardize column names based on your verified file structures
        sem_wise_df.rename(columns={'Course Number': 'CourseNo'}, inplace=True)
        slotwise_df.rename(columns={'BaseCourseNo': 'CourseNo'}, inplace=True)
        course_type_df.rename(columns={'Code': 'Category', 'Course Category': 'CourseType'}, inplace=True)
        
        print("✅ Step 2: Standardized column names for merging.")

        # 3. Merge the core dataframes
        master_df = pd.merge(sem_wise_df, slotwise_df[['CourseNo', 'Slot']], on='CourseNo', how='left')
        master_df = pd.merge(master_df, course_type_df[['Category', 'CourseType']], on='Category', how='left')
        
        print("✅ Step 3: Merged core course information.")

        # 4. Clean the data by removing duplicate course entries
        master_df.drop_duplicates(subset='CourseNo', keep='first', inplace=True)
        
        print("✅ Step 4: Removed duplicate courses.")

        # 5. Integrate the accurate prerequisite data
        new_prereqs_df = pd.read_csv(io.StringIO(prerequisite_data))
        final_df = pd.merge(master_df, new_prereqs_df, on='CourseNo', how='left')
        
        print("✅ Step 5: Integrated accurate prerequisite data.")

        # 6. Save the final knowledge base to your Drive
        output_path = base_path + 'master_course_catalog_final.csv'
        final_df.to_csv(output_path, index=False)
        
        print("\n--- Knowledge Base Created Successfully ---")
        print(f"The final, clean file has been saved as: {output_path}")
        
        return final_df

    except FileNotFoundError as e:
        print(f"❌ Error: A file was not found. Please check your paths.")
        print(f"File not found: {e.filename}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    master_catalog = create_knowledge_base()
    if master_catalog is not None:
        print("\nHere is a preview of the final, clean data:")
        print(master_catalog.head())