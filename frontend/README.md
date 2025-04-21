# Serverless Execution Platform Frontend

This is the frontend application for the Serverless Execution Platform, built with Streamlit.

## Features

- Function Management
  - Create new functions
  - View existing functions
  - Update and delete functions
- Monitoring Dashboard
  - System-wide statistics
  - Function performance metrics
  - Visual performance charts

## Setup

1. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start the application:
```bash
streamlit run app.py
```

## Configuration

The frontend is configured to connect to the backend API at `http://localhost:8000` by default. If your backend is running on a different URL, update the `API_BASE_URL` in `app.py`.

## Usage

1. Open your web browser and navigate to `http://localhost:8501`
2. Use the sidebar to navigate between Function Management and Monitoring Dashboard
3. Create, view, update, and delete functions as needed
4. Monitor system performance and function execution metrics

## Development

- The application is built using Streamlit
- Main application logic is in `app.py`
- Dependencies are listed in `requirements.txt` 