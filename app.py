from flask import Flask, request, jsonify, render_template_string
import pandas as pd
import pdfplumber
import re
import io
import datetime

# Initialize the Flask App
app = Flask(__name__)

# --- Global variable to hold our knowledge base ---
COURSE_CATALOG = None
TIMETABLES = None

# --- DATA PROCESSING & KNOWLEDGE BASE CREATION ---

def create_knowledge_base():
    """
    Loads, cleans, and merges all data sources into a unified pandas DataFrame.
    This runs once when the server starts.
    """
    try:
        # Load all source data
        sem_wise_df = pd.read_csv('sem_wise_details.csv')
        slotwise_df = pd.read_csv('slotwise_details.csv')
        course_type_df = pd.read_csv('course_type.csv')

        # Standardize column names
        sem_wise_df.rename(columns={'Course Number': 'CourseNo'}, inplace=True)
        slotwise_df.rename(columns={'BaseCourseNo': 'CourseNo', 'Prerequisite': 'Prerequisites'}, inplace=True)
        course_type_df.rename(columns={'Code': 'Category', 'Course Category': 'CourseType'}, inplace=True)

        # Merge dataframes
        slotwise_subset = slotwise_df[['CourseNo', 'Slot', 'Prerequisites']]
        course_type_subset = course_type_df[['Category', 'CourseType']]
        
        master_df = pd.merge(sem_wise_df, slotwise_subset, on='CourseNo', how='left')
        master_df = pd.merge(master_df, course_type_subset, on='Category', how='left')

        # Clean and deduplicate
        master_df.drop_duplicates(subset='CourseNo', keep='first', inplace=True)
        master_df['Prerequisites'] = master_df['Prerequisites'].fillna('None')
        
        print("✅ Knowledge base created successfully.")
        return master_df

    except Exception as e:
        print(f"❌ Error creating knowledge base: {e}")
        return None

def load_timetables():
    """Loads the timetable structures into a dictionary."""
    # In a real app, this might come from a file, but we can define it here
    return {
        "senior": {
            "B": ["Monday", "Wednesday", "Thursday", "Friday"], "C": ["Monday", "Tuesday", "Thursday", "Friday"],
            "D": ["Monday", "Tuesday", "Wednesday", "Friday"], "F": ["Monday", "Thursday", "Friday"],
            "G": ["Monday", "Tuesday", "Thursday"], "A": ["Tuesday", "Wednesday", "Thursday"],
            "H": ["Tuesday", "Wednesday"]
        },
        "first_year": {
            "A1": ["Monday"], "B1": ["Monday"], "C1": ["Monday"], "D1": ["Monday"],
            "A2": ["Tuesday"], "B2": ["Tuesday"], "C2": ["Tuesday"], "D2": ["Tuesday"],
            # ... and so on for all first-year slots
        }
    }

# --- PDF & PROFILE ANALYSIS LOGIC ---

def calculate_semester_and_year(roll_no):
    """Calculates current semester and year from a roll number."""
    match = re.search(r'[A-Z]{2}(\d{2})', roll_no)
    if not match: return 1, 1
    
    entry_year = int("20" + match.group(1))
    current_year = datetime.datetime.now().year
    current_month = datetime.datetime.now().month
    
    year_diff = current_year - entry_year
    student_year = year_diff + 1
    
    if current_month >= 7: # Jul-Nov session
        semester = year_diff * 2 + 1
    else: # Jan-May session
        semester = year_diff * 2
        
    return semester, student_year

def parse_grade_card(file_stream):
    """Extracts student profile and completed courses from a PDF file stream."""
    text = ""
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
            
    roll_no = re.search(r"Roll No:\s*([A-Z0-9]+)", text).group(1)
    name = re.search(r"Name:\s*([A-Z\s]+)", text).group(1).strip()
    department = re.search(r"Department:\s*([A-Za-z\s]+)", text).group(1).strip()
    
    semester, year = calculate_semester_and_year(roll_no)
    
    return {"rollNo": roll_no, "name": name, "department": department, "semester": semester, "year": year}


# --- FLASK API ENDPOINTS ---

@app.route('/')
def index():
    # This serves the main HTML file
    return render_template_string(open('index.html').read())

@app.route('/api/init_from_pdf', methods=['POST'])
def init_from_pdf():
    """
    Receives a grade card, parses it, and returns mandatory courses and occupied slots.
    """
    if 'gradeCard' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['gradeCard']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        student_profile = parse_grade_card(file)
        
        # Find mandatory courses for this student
        dept_code_map = {"Civil Engineering": "CE"} # Can be expanded
        dept_code = dept_code_map.get(student_profile['department'], 'XX')
        
        mandatory_courses = COURSE_CATALOG[
            (COURSE_CATALOG['Department'] == dept_code) &
            (COURSE_CATALOG['Semester'] == student_profile['semester']) &
            (~COURSE_CATALOG['Category'].isin(['H', 'M', 'FRE', 'MNS'])) # Not electives
        ]
        
        occupied_slots = mandatory_courses['Slot'].dropna().unique().tolist()
        
        return jsonify({
            "studentProfile": student_profile,
            "mandatoryCourses": mandatory_courses.to_dict('records'),
            "occupiedSlots": occupied_slots
        })

    except Exception as e:
        return jsonify({"error": f"Failed to process PDF: {str(e)}"}), 500

@app.route('/api/recommend_electives', methods=['POST'])
def recommend_electives():
    """
    Recommends electives based on user preference and free slots.
    """
    data = request.json
    preference = data.get('preference')
    occupied_slots = data.get('occupiedSlots', [])
    
    # Filter for electives
    elective_courses = COURSE_CATALOG[COURSE_CATALOG['Category'].isin(['H', 'M', 'FRE', 'MNS'])]
    
    # Filter by preference (keyword search in course name)
    if preference and preference.lower() != 'any':
        elective_courses = elective_courses[elective_courses['Course Name'].str.contains(preference, case=False, na=False)]
        
    # Filter out courses in occupied slots
    free_electives = elective_courses[~elective_courses['Slot'].isin(occupied_slots)]
    
    # Rank and select top 5
    recommendations = free_electives.head(5).to_dict('records')
    
    return jsonify({"recommendations": recommendations})


# --- Pre-load data when the application starts ---
COURSE_CATALOG = create_knowledge_base()
TIMETABLES = load_timetables()

if __name__ == "__main__":
    app.run(debug=True)
