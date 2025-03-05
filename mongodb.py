import io
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pymongo import MongoClient
from datetime import datetime
import base64
import random
import pdfkit
import os

# MongoDB connection details
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "nar"  
COLLECTION_NAME = "candidate_call_report"  

# Function to fetch data
@st.cache_data
def fetch_mongo_data_and_form_types(start_date, end_date):
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        # Convert selected dates to MongoDB format (ISODate)
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

        # MongoDB Aggregation Pipeline
        pipeline = [
            {
                "$lookup": {
                    "from": "call-logs",
                    "localField": "callLog",
                    "foreignField": "_id",
                    "as": "callLog"
                }
            },
            {"$unwind": "$callLog"},
            {
                "$replaceRoot": { 
                    "newRoot": {
                        "$mergeObjects": [
                            "$$ROOT",
                            "$callLog",
                            "$callLog.candidate-response",
                            "$callLog.candidate-response.question"
                        ]
                    }
                }
            },
            {
                "$match": {
                    "date": {"$gte": start_date, "$lte": end_date}  # Filter by date range
                }
            },
            {
                "$project": {
                    "callLog": 0,
                    "candidate-response": 0,
                    "question": 0,
                    "_id": 0,
                    "__v": 0
                }
            },
            {
                "$addFields": {
                    "updatedDate": {
                        "$add": ["$date", 19800000]  # Convert UTC to IST (5:30 hrs)
                    }
                }
            },
            {
                "$addFields": {
                    "dateUpdate": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$updatedDate"}
                    },
                    "time": {
                        "$dateToString": {"format": "%H:%M:%S", "date": "$updatedDate"}
                    }
                }
            }
        ]

        # Fetch data using aggregation
        data = list(collection.aggregate(pipeline))
        if not data:
            return [], pd.DataFrame()

        # Separate data based on `formType`
        separated_data = {}
        for record in data:
            form_type = record.get('formType', 'default-form')
            separated_data.setdefault(form_type, []).append(record)

        # Convert separated data into DataFrames
        df_list = [pd.DataFrame(value) for key, value in separated_data.items()]

        # Fetch distinct formType values
        form_type_df = pd.DataFrame({"Form Type": list(separated_data.keys())})  

        return df_list, form_type_df  

    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return [], pd.DataFrame()

def fetch_form_questions(form_name):
    try:    
        client = MongoClient(MONGO_URI)  # Connect to MongoDB
        db = client[DB_NAME]
        collection = db['forms']

        # Define the aggregation pipeline
        form_pipeline = [
            {
                "$match": {
                    "formName": form_name  # Filter for the specific form
                }
            },
            {
                "$unwind": {
                    "path": "$fields"
                }
            },
            {
                "$project": {
                    "question": "$fields.label"
                }
            }
        ]

        # Execute the pipeline and fetch data
        data = list(collection.aggregate(form_pipeline))

        client.close()  # Close the MongoDB connection

        # Extract only questions
        questions = [record.get("question") for record in data]

        return questions  # Returns only questions for the specified form

    except Exception as e:
        print(f"Error fetching questions: {e}")  # Print error for debugging
        return []  # Return an empty list in case of failure

# Streamlit UI
st.set_page_config(
    page_title="📞 NAR Calling Report",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",  # Collapsed sidebar for more space
    menu_items={
        'Get Help': 'https://your-help-link.com',  # Replace with your support link
        'Report a bug': 'https://your-bug-report-link.com',  # Replace with your bug report link
        'About': """
            ## 📊 NAR Calling Report
            This dashboard provides insightful visualizations and analytics for call records.
            Developed by [patio digital](https://your-link.com).
        """
    }
)

def get_base64_of_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()
    
logo_left = get_base64_of_image("C:\\Users\\91810\\OneDrive\\Desktop\\Patio-logo.png")
logo_right = get_base64_of_image("C:\\Users\\91810\\OneDrive\\Desktop\\NAR logo2.png")

# Injecting custom HTML and CSS for positioning logos

st.markdown(
    f"""
    <style>
        .logo-container {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px;
        }}
        .logo-container img {{
            width: 120px;
        }}
    </style>
    <div class="logo-container">
        <img src="data:image/png;base64,{logo_left}">
        <img src="data:image/png;base64,{logo_right}">
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.subheader("📅 Select Date Range")

# Sidebar Date Selection
start_date = st.sidebar.date_input("Start Date", datetime.today())
end_date = st.sidebar.date_input("End Date", datetime.today())

# Convert to string format
start_date_str = start_date.strftime("%Y-%m-%d")
end_date_str = end_date.strftime("%Y-%m-%d")

data_df_list = []  # Store DataFrames from MongoDB
form_type_df = None  # Store Form Type DataFrame

if st.sidebar.button("Fetch Data"):
    # Fetch data and store in session state
    data_df_list, form_type_df = fetch_mongo_data_and_form_types(start_date_str, end_date_str)
    st.session_state["data_df_list"] = data_df_list  # Store data in session state

    # Extract unique form types
    form_types = sorted({
        df["formType"].iloc[0] if "formType" in df.columns and not df["formType"].isna().all() else "default-form"
        for df in data_df_list if not df.empty
    })

    # Store form types in session state
    st.session_state["form_types"] = form_types

# Check if data is available in session state
if "data_df_list" in st.session_state and "form_types" in st.session_state:
    data_df_list = st.session_state["data_df_list"]
    form_types = st.session_state["form_types"]

    # Sidebar dropdown for selecting a specific form type
    selected_form = st.sidebar.selectbox("Select Form Type", ["All Forms"] + form_types)
    
form_count = 0

for df in data_df_list:
    if df.empty:
        continue
    
    form_type = df["formType"].iloc[0] if "formType" in df.columns and not df["formType"].isna().all() else "default-form"

    if selected_form != "All Forms" and form_type != selected_form:
        continue

    if form_count > 0:
        print(form_count)
    # Use a styled div for page break
        st.markdown(
            f"""
            <div style="page-break-before: always;"></div>
            <style>
                .logo-container {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .logo-container img {{
                    width: 140px;
                }}
                .page-break {{
                    page-break-after: always;
                    display: block;
                    margin: 40px 0;
                }}
            </style>
            <div class="logo-container">
                <img src="data:image/png;base64,{logo_left}">
                <img src="data:image/png;base64,{logo_right}">
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown(
        f"""
        <div style="
            text-align: center; 
            padding: 10px; 
            background: linear-gradient(to right, #87CEEB, #4682B4); 
            border-radius: 12px; 
            border: 2px solid #1C2833;
            box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.25);
        ">
            <h1 style="
                font-size: 38px; 
                font-family: 'Playfair Display', sans-serif; 
                font-weight: 800; 
                color: white; 
                text-transform: uppercase;
                letter-spacing: 1.5px;
                margin-bottom: 5px;
                text-shadow: 3px 3px 8px rgba(0, 0, 0, 0.3);
            ">
                <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="#6B8E23">
                <path d="M6.62 10.79a15.91 15.91 0 0 0 6.59 6.59l2.2-2.2a1.5 1.5 0 0 1 1.49-.39c1.6.4 3.31.61 5.1.61a1.5 1.5 0 0 1 1.5 1.5V21a1.5 1.5 0 0 1-1.5 1.5c-10.49 0-19-8.51-19-19A1.5 1.5 0 0 1 3 3h3.5a1.5 1.5 0 0 1 1.5 1.5c0 1.79.21 3.5.61 5.1a1.5 1.5 0 0 1-.39 1.49l-2.2 2.2z"/>
                </svg>
                Nar Calling Report
            </h1>
            <h3 style="
                color: white; 
                font-family: 'Playfair Display', serif; 
                font-weight: 700; 
                font-size: 28px; 
                letter-spacing: 1.2px; 
                text-transform: capitalize; 
                margin-bottom: 5px; 
                opacity: 1; 
                text-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);
            ">
                {start_date_str} to {end_date_str}
            </h3>
        </div>
        """, 
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div style="
            margin: 20px auto;  /* Adds spacing around the box */
            padding: 15px; 
            background: linear-gradient(135deg, #1E3A8A, #4682B4); 
            border-radius: 12px;  
            border: 3px solid black;  /* Bold black border */
            box-shadow: 5px 5px 20px rgba(0, 0, 0, 0.3);
            text-align: center;
            color: white;
            max-width: 80%;
        ">
            <h2 style="
                font-size: 26px; 
                font-weight: 800; 
                margin: 10px 0;
                text-transform: uppercase;
                letter-spacing: 1.2px;
                font-family: 'Arial', sans-serif;
                text-shadow: 3px 3px 6px rgba(0, 0, 0, 0.3);
            ">
                📋 Report - {form_type}
            </h2>
        </div>
        """, 
        unsafe_allow_html=True
    )
    form_count += 1 

    # Fetch form questions
    form_questions = [ item.replace(' ', '-') for item in fetch_form_questions(form_type) ]
    
    columns_to_plot = ["call-answered", "call_status","call-type"] + list(form_questions)
    
    valid_chart_count = 0 
    
    skip_columns = ["monthly_income_value", "Amount of Finance Availed", "What additional Help needed from RSETI?"]
    skip_columns = [col.replace(" ", "-") for col in skip_columns]

    for i, column in enumerate(columns_to_plot):
        
        if column in skip_columns:
            continue

        if column in df.columns:
            # Filter out None, NaN, and blank values
            filtered_values = df[column].dropna()
            filtered_values = filtered_values[filtered_values.astype(str).str.strip() != ""]

            if filtered_values.empty:
                continue  # Skip this column and move to the next one

            # Get value counts from filtered data
            value_counts = filtered_values.value_counts()

            if value_counts.empty:
                continue

            total_count = value_counts.sum()  # Get total count

                # Create labels with counts
            labels_counts = [f"{label} ({count})" for label, count in zip(value_counts.index, value_counts.values)]

            # Create Pie Chart
            fig = go.Figure(data=[go.Pie(
                    labels=labels_counts,
                    values=value_counts.values,
                    hole=0.3,
                    textinfo='percent',  # Show percentage
                    insidetextorientation='radial'
                )])

            fig.update_layout(
                        height=600,  # Height of the pie chart
                        width=900,  # Width of the pie chart
                        showlegend=True,  # Ensure the legend is visible
                        legend_title=dict(
                            text=f"<b style='font-size:18px; color:#FF8C00;'>Total Count: {total_count}</b>",  # Increase size & bold text
                            font=dict(size=18, color="#FF8C00"),  # Dark grey color for better visibility
                        ),
                        legend=dict(
                            orientation="v",  # Vertical legend layout
                            yanchor="top",
                            y=-0.1,  # Move the legend below the pie chart
                            xanchor="center",
                            x=0.5,  # Center-align legend
                            font=dict(size=16, color="#4B5563"),  # Increase font size for labels
                            bgcolor="rgba(255,255,255,1)",  # Pure white colo
                            bordercolor="#E5E7EB",  # Subtle gray border
                            borderwidth=1.5,  # Slight border for distinction
                    ),
                        margin=dict(t=50, b=150, l=50, r=50),  # Add extra margin at the bottom for the legend
                        plot_bgcolor="rgba(0,0,0,0)",  # Transparent background for the chart area
                        paper_bgcolor="rgba(255,255,255,1)",  # White background for the figure
                    )

            fig.update_layout(
                    legend=dict(
                    traceorder="normal",  # Keep labels in the same order as data
                    valign="middle",  # Vertically align items to the middle of the space
                    itemwidth=75,  # Increase the horizontal space for each label 
                    )
                )

            # Remove scrolling by dynamically adjusting height for the legend
            max_legend_rows = len(value_counts) // 3 + 1  # Dynamically calculate rows based on labels
            fig.update_layout(height=600 + max_legend_rows * 40,)  # Increase height to fit all labels
    
            # Styled title box
            if valid_chart_count % 3 == 0:
                chart_cols = st.columns(3)
                
            with chart_cols[valid_chart_count % 3]:  # Ensures correct column placement
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(to right, #2F4F7F, #2F4F7F);
                        padding: 8px;
                        border-radius: 8px;
                        text-align: center;
                        font-weight: bold;
                        color: white;
                        font-size: 18px;
                        text-transform: uppercase;
                        box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
                        margin-bottom: -10px;
                    ">
                        {column.replace("_", " ").replace("-", " ")}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                # Display Pie Chart
                st.plotly_chart(fig, use_container_width=True,key=random.randint(1, 1000000))
            # Create an in-memory buffer
                buffer = io.BytesIO()

                # Save the figure as a PDF to the buffer
                fig.write_image(file=buffer, format="pdf")

                # Download the PDF from the buffer
                st.download_button(
                    label="Download PDF",
                    data=buffer,
                    file_name="market_figure.pdf",
                    mime="application/pdf",key=random.randint(1, 1000005)
                )
                
            valid_chart_count += 1 

            
            # Insert page break only if there were charts on this page
            if valid_chart_count % 6 == 0 and valid_chart_count < len(form_questions):
                print("Page Break Here")
                st.markdown(
                    f"""
                    '<div style="page-break-before: always;"></div>'
                    <style>
                        .logo-container {{
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                            padding: 20px;
                            margin: 20px 0;
                        }}
                        .logo-container img {{
                            width: 140px;
                        }}
                        .page-break {{
                            page-break-after: always;
                            display: block;
                            margin: 40px 0;
                        }}
                    </style>
                    <div class="logo-container">
                        <img src="data:image/png;base64,{logo_left}">
                        <img src="data:image/png;base64,{logo_right}">
                    </div>
                    """,
                    unsafe_allow_html=True
                )
 
# Path to wkhtmltopdf executable (Update this path)
# pdfkit_config = pdfkit.configuration(wkhtmltopdf='C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe')

# # Capture HTML content dynamically using Streamlit's built-in methods
# def capture_html():
#     # Create HTML content for the PDF
#     st.session_state["html_content"] = """
#     <html>
#     <head>
#         <style>
#             body { font-family: Arial, sans-serif; padding: 20px; }
#             h2 { color: #1E3A8A; text-align: center; }
#             st.chart-container { text-align: center; margin: 20px 0; }
#         </style>
#     </head>
#     <body>
#         <h2>Dashboard Report</h2>
#     """

#     # Append your charts and data as HTML
#     for df in st.session_state.get("data_df_list", []):
#         if df.empty:
#             continue
#         # Convert DataFrame to HTML
#         st.session_state["html_content"] += df.to_html(index=False, border=1)

#     st.session_state["html_content"] += "</body></html>"

# # Generate PDF from HTML content
# def create_pdf_from_html():
#     html_string = st.session_state.get("html_content", "")
    
#     if not html_string:
#         st.warning("Please fetch data first to enable download.")
#         return None

#     # Generate PDF
#     pdf_file = "dashboard_report.pdf"
#     pdfkit.from_string(html_string, pdf_file, configuration=pdfkit_config)
#     return pdf_file

# # Download PDF button
# def download_pdf_button():
#     pdf_file = create_pdf_from_html()
#     if pdf_file and os.path.exists(pdf_file):
#         with open(pdf_file, "rb") as f:
#             pdf_data = f.read()

#         # Encode PDF to base64 for download
#         b64_pdf = base64.b64encode(pdf_data).decode("utf-8")
#         download_button_str = f"""
#         <a href="data:application/pdf;base64,{b64_pdf}" download="dashboard_report.pdf">
#             <button style="
#                 background-color: #1E3A8A; 
#                 color: white; 
#                 padding: 10px 20px; 
#                 border: none; 
#                 border-radius: 8px; 
#                 font-size: 16px; 
#                 cursor: pointer; 
#                 box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.3);
#             ">
#                 📥 Download PDF
#             </button>
#         </a>
#         """
#         # Display the button in the sidebar
#         st.sidebar.markdown(download_button_str, unsafe_allow_html=True)

# # Run the HTML capture function after fetching data
# if "data_df_list" in st.session_state:
#     capture_html()  # Save HTML content to session state

# # Show the download button
# download_pdf_button()

# from streamlit.components.v1 import html

# my_js = """
# console.log(document.documentElement.parentElement);
# """

# my_html = f"""<script>{my_js}</script></div>"""

# # Execute your app
# st.title("Javascript example")
# html(my_html)