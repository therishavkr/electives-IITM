from flask import Flask, request, jsonify, render_template_string
import pandas as pd
import pdfplumber
import re
import datetime

app = Flask(__name__)

# --- In-memory storage for data and user sessions ---
COURSE_CATALOG = None
STUDENT_SESSIONS = {} 

def load_knowledge_base():
    """Loads the pre-processed course catalog from the CSV file."""
    global COURSE_CATALOG
    try:
        COURSE_CATALOG = pd.read_csv('master_course_catalog_final.csv')
        # Ensure 'Description' column exists and is a string for safe searching
        if 'Description' not in COURSE_CATALOG.columns:
            COURSE_CATALOG['Description'] = ""
        COURSE_CATALOG['Description'] = COURSE_CATALOG['Description'].fillna('')
        print("✅ Knowledge base loaded successfully.")
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Could not load knowledge base: {e}")

def parse_grade_card(file_stream):
    """
    Extracts a detailed student profile from the grade card, including name,
    roll number, CGPA, and a list of all courses taken with grades.
    """
    text = ""
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    profile = {
        "rollNo": re.search(r"Roll No:\s*([A-Z0-9]+)", text).group(1),
        "name": re.search(r"Name:\s*([A-Z\s]+)", text).group(1).strip(),
        "department": re.search(r"Department:\s*([A-Za-z\s]+)", text).group(1).strip(),
        "cgpa": float(re.search(r"average secured.*?is\s*([\d\.]+)", text).group(1)),
        "courses_taken": []
    }
    
    # This regex is designed to capture course rows like: "CS1100","Intro to Prog","12","A"
    course_pattern = re.compile(r'\"([A-Z]{2}\d{3,}[A-Z]*C?)\s*\",\"(.*?)\",\"(\d+)?\",\"([A-Z]{1,2})?\"')
    matches = course_pattern.findall(text)
    for match in matches:
        # Ensure all parts of the match are captured, provide defaults if not
        course_no, title, credits, grade = match
        profile["courses_taken"].append({
            "course_no": course_no,
            "title": title.replace('"', ''),
            "credits": int(credits) if credits else 0,
            "grade": grade if grade else 'N/A'
        })

    # Calculate semester and save the entire profile to the session
    profile["semester"], _ = calculate_semester_and_year(profile["rollNo"])
    STUDENT_SESSIONS[profile["rollNo"]] = profile
    print(f"✅ Profile for {profile['name']} ({profile['rollNo']}) created and saved.")
    return profile

def calculate_semester_and_year(roll_no):
    """Calculates the current semester and academic year from a roll number."""
    match = re.search(r'[A-Z]{2}(\d{2})', roll_no)
    if not match: return 1, 1
    entry_year = int("20" + match.group(1))
    current_year = datetime.datetime.now().year
    month = datetime.datetime.now().month
    year_diff = current_year - entry_year
    semester = year_diff * 2 + (1 if month >= 7 else 0)
    return semester if semester > 0 else 1, year_diff + 1

def generate_suggested_questions(profile):
    """Generates personalized suggested questions based on the student's history."""
    suggestions = ["Suggest some 9 credit electives"]
    
    # Analyze course history for interests
    humanities_count = sum(1 for course in profile['courses_taken'] if course['course_no'].startswith('HS'))
    if humanities_count >= 2:
        suggestions.append("Show me more humanities electives in my free slots")
    else:
        suggestions.append("Suggest some humanities courses for me")
        
    suggestions.append("Find management electives")
    return suggestions

@app.route('/')
def index():
    """Serves the main HTML page for the chatbot."""
    return render_template_string(open('index.html').read())

@app.route('/api/init_from_pdf', methods=['POST'])
def init_from_pdf():
    """Handles the grade card upload, analyzes it, and starts the session."""
    if 'gradeCard' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['gradeCard']
    try:
        student_profile = parse_grade_card(file)
        
        dept_code_map = {"Civil Engineering": "CE", "Aerospace Engineering": "AE"} # Can be expanded
        dept_code = dept_code_map.get(student_profile['department'], 'XX')
        
        mandatory_courses = COURSE_CATALOG[
            (COURSE_CATALOG['Department'] == dept_code) &
            (COURSE_CATALOG['Semester'] == student_profile['semester']) &
            (~COURSE_CATALOG['Category'].isin(['H', 'M', 'FRE', 'MNS'])) # Filter out electives
        ]
        occupied_slots = mandatory_courses['Slot'].dropna().unique().tolist()
        
        # Save the occupied slots to the user's session
        STUDENT_SESSIONS[student_profile['rollNo']]['occupied_slots'] = occupied_slots
        
        return jsonify({
            "studentProfile": student_profile,
            "suggestedQuestions": generate_suggested_questions(student_profile)
        })
    except Exception as e:
        return jsonify({"error": f"Failed to process PDF. Please ensure it's a valid grade card. Details: {str(e)}"}), 500

@app.route('/api/recommend_electives', methods=['POST'])
def recommend_electives():
    """Provides elective recommendations based on user query and performance analysis."""
    data = request.json
    query = data.get('preference', '').lower()
    roll_no = data.get('rollNo')
    
    if not roll_no or roll_no not in STUDENT_SESSIONS:
        return jsonify({"error": "Session not found. Please upload your grade card again."}), 400

    student_profile = STUDENT_SESSIONS[roll_no]
    occupied_slots = student_profile.get('occupied_slots', [])
    
    # Start with all available electives
    results = COURSE_CATALOG[COURSE_CATALOG['Category'].isin(['H', 'M', 'FRE', 'MNS'])]

    # --- Performance-Based Filtering Logic ---
    has_poor_coding_perf = any(
        course['course_no'].startswith('CS') and course['grade'] in ['C', 'D', 'E']
        for course in student_profile['courses_taken']
    )
    
    # If student is not from CS/AI and has poor coding grades, filter out technical courses
    if has_poor_coding_perf and student_profile['department'] not in ['Computer Science', 'AI & DS']:
        print(f"⚠️ Poor coding performance detected for {roll_no}. Filtering out technical electives.")
        coding_keywords = ['programming', 'data', 'algorithm', 'software', 'computing', 'machine learning']
        pattern = '|'.join(coding_keywords)
        results = results[
            ~results['Course Name'].str.contains(pattern, case=False, na=False) &
            ~results['Description'].str.contains(pattern, case=False, na=False)
        ]

    # --- NLU-like Search on remaining courses ---
    if query:
        results = results[
            results['Course Name'].str.contains(query, case=False, na=False) |
            results['CourseType'].str.contains(query, case=False, na=False) |
            results['Description'].str.contains(query, case=False, na=False)
        ]

    # Find electives that are in free slots
    free_electives = results[~results['Slot'].isin(occupied_slots)]
    recommendations = free_electives.head(5).to_dict('records')
    return jsonify({"recommendations": recommendations})

# Load the knowledge base once when the application starts
load_knowledge_base()

