import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
from datetime import datetime
import tempfile
import os
import uuid
from pathlib import Path
import time

# Page configuration
st.set_page_config(
    page_title="Serverless Execution Platform",
    page_icon="🚀",
    layout="wide"
)

# API configuration
API_BASE_URL = "http://localhost:8000"  # Update this with your actual API URL

# Create functions directory if it doesn't exist
FUNCTIONS_DIR = Path("functions")
FUNCTIONS_DIR.mkdir(parents=True, exist_ok=True)

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Function Management", "Monitoring Dashboard"])

# Function Management Page
if page == "Function Management":
    st.title("Function Management")
    
    # Function creation form
    with st.expander("Create New Function", expanded=True):
        with st.form("create_function_form"):
            function_name = st.text_input("Function Name")
            function_code = st.text_area("Function Code", height=200)
            
            # Add configuration options
            col1, col2 = st.columns(2)
            with col1:
                timeout = st.selectbox(
                    "Timeout (seconds)",
                    options=[10, 30, 60, 120, 300],
                    index=1  # Default to 30 seconds
                )
            with col2:
                memory = st.selectbox(
                    "Memory (MB)",
                    options=[128, 256, 512, 1024],
                    index=0  # Default to 128 MB
                )
            
            submit_button = st.form_submit_button("Create Function")
            
            if submit_button:
                try:
                    # Generate a unique filename
                    function_id = str(uuid.uuid4())
                    function_filename = f"function_{function_id}.py"
                    function_path = FUNCTIONS_DIR / function_filename
                    
                    # Ensure the functions directory exists
                    FUNCTIONS_DIR.mkdir(parents=True, exist_ok=True)
                    
                    # Save the function code to a file with proper encoding
                    with open(function_path, "w", encoding='utf-8') as f:
                        f.write(function_code)
                    
                    # Get absolute path for the API
                    absolute_path = str(function_path.absolute())
                    
                    # Send the request with the code_path
                    response = requests.post(
                        f"{API_BASE_URL}/functions",
                        json={
                            "name": function_name,
                            "code_path": absolute_path,
                            "runtime": "python",
                            "timeout": timeout,
                            "memory": memory
                        }
                    )
                    
                    if response.status_code == 201:  # 201 Created
                        st.success("Function created successfully!")
                    else:
                        # If creation fails, clean up the file
                        if function_path.exists():
                            function_path.unlink()
                        st.error(f"Error creating function: {response.text}")
                except Exception as e:
                    # Clean up the file if it exists
                    if function_path.exists():
                        function_path.unlink()
                    st.error(f"Error creating function: {str(e)}")
    
    # Function list
    st.subheader("Existing Functions")
    try:
        try:
            response = requests.get(f"{API_BASE_URL}/functions")
            if response.status_code == 200:
                functions = response.json()
                if functions:
                    for func in functions:
                        with st.expander(f"Function: {func['name']} (Timeout: {func['timeout']}s, Memory: {func['memory']}MB)"):
                            # Read and display the function code
                            try:
                                with open(func['code_path'], 'r', encoding='utf-8') as f:
                                    code_content = f.read()
                                st.code(code_content, language='python')
                            except Exception as e:
                                st.error(f"Error reading function code: {str(e)}")
                            
                            # Add execution options
                            st.subheader("Execute Function")
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                runtime = st.selectbox(
                                    "Runtime",
                                    options=["cli", "docker", "gvisor"],  # CLI first as default
                                    index=0,  # Default to CLI
                                    key=f"runtime_{func['id']}"
                                )
                            
                            with col2:
                                warmup = st.checkbox("Warmup", key=f"warmup_{func['id']}")
                            
                            with col3:
                                if st.button("Execute", key=f"execute_{func['id']}"):
                                    try:
                                        with st.spinner("Executing function - this may take a while..."):
                                            execution_response = requests.post(
                                                f"{API_BASE_URL}/functions/{func['id']}/execute",
                                                json={
                                                    "data": {
                                                        "args": [],
                                                        "kwargs": {}
                                                    }
                                                }
                                            )
                                            
                                            if execution_response.status_code == 200:
                                                result = execution_response.json()
                                                st.success("Function executed successfully!")
                                                
                                                # Display pod name
                                                pod_name = result.get("pod_name")
                                                if pod_name:
                                                    st.info(f"Pod name: {pod_name}")
                                                
                                                # Display logs
                                                if "logs" in result:
                                                    st.code(result["logs"], language="text")
                                                else:
                                                    st.warning("No logs available")
                                            else:
                                                st.error(f"Error executing function: {execution_response.text}")
                                    except Exception as e:
                                        st.error(f"Error executing function: {str(e)}")
                            
                            # Function management buttons
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Update", key=f"update_{func['id']}"):
                                    # TODO: Implement update functionality
                                    pass
                            with col2:
                                if st.button("Delete", key=f"delete_{func['id']}"):
                                    try:
                                        delete_response = requests.delete(f"{API_BASE_URL}/functions/{func['id']}")
                                        if delete_response.status_code == 204:
                                            # Clean up the function file
                                            function_path = Path(func['code_path'])
                                            if function_path.exists():
                                                function_path.unlink()
                                            st.success("Function deleted successfully!")
                                            st.rerun()
                                        else:
                                            st.error(f"Error deleting function: {delete_response.text}")
                                    except Exception as e:
                                        st.error(f"Error deleting function: {str(e)}")
                else:
                    st.info("No functions found. Create one above!")
            else:
                st.warning(f"Error fetching functions: {response.text}")
                st.info("No functions found. Create one above!")
        except Exception as e:
            st.warning(f"Error connecting to API: {str(e)}")
            st.info("No functions found. Create one above!")
    except Exception as e:
        st.warning(f"An unexpected error occurred: {str(e)}")
        st.info("No functions found. Create one above!")

# Monitoring Dashboard Page
elif page == "Monitoring Dashboard":
    st.title("Monitoring Dashboard")
    
    # Time period selector
    time_period = st.selectbox(
        "Time Period",
        options=[7, 14, 30, 60, 90],
        index=2,  # Default to 30 days
        format_func=lambda x: f"Last {x} days"
    )
    
    # System-wide statistics
    st.subheader("System Statistics")
    
    try:
        # Get system metrics
        response = requests.get(f"{API_BASE_URL}/metrics?days={time_period}")
        if response.status_code == 200:
            metrics = response.json()
            
            # Main metrics in cards
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Active Functions", metrics.get('active_functions', 0))
            with col2:
                st.metric("Total Executions", metrics.get('total_executions', 0))
            with col3:
                # Fix the success rate calculation
                total_execs = metrics.get('total_executions', 0)
                success_execs = metrics.get('successful_executions', 0)
                if total_execs > 0:
                    success_rate = (success_execs / total_execs) * 100
                else:
                    success_rate = 0
                st.metric("Success Rate", f"{success_rate:.1f}%")
            with col4:
                st.metric("Avg Execution Time", f"{metrics.get('avg_execution_time', 0):.2f}s")
            
            # Time series data
            st.subheader("Execution Trends")
            time_series_data = metrics.get('time_series', [])
            if time_series_data and len(time_series_data) > 0:
                try:
                    # Convert to dataframe for plotting
                    df_time_series = pd.DataFrame(time_series_data)
                    if not df_time_series.empty and 'date' in df_time_series.columns and 'executions' in df_time_series.columns:
                        df_time_series['date'] = pd.to_datetime(df_time_series['date'])
                        
                        # Plot time series
                        fig = px.line(
                            df_time_series, 
                            x='date', 
                            y='executions',
                            labels={'date': 'Date', 'executions': 'Number of Executions'},
                            title=f"Function Executions over the Last {time_period} Days"
                        )
                        fig.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Time series data format is incomplete.")
                except Exception as e:
                    st.warning(f"Error displaying time series chart: {str(e)}")
                    st.info("Time series data is available but couldn't be displayed properly.")
            else:
                st.info("No time series data available yet.")
            
            # Function performance
            st.subheader("Function Performance")
            performance_data = metrics.get('function_performance', [])
            if performance_data and len(performance_data) > 0:
                try:
                    df_performance = pd.DataFrame(performance_data)
                    if not df_performance.empty and 'function_name' in df_performance.columns:
                        # Create two columns for the charts
                        chart_col1, chart_col2 = st.columns(2)
                        
                        with chart_col1:
                            if 'execution_time' in df_performance.columns:
                                # Execution time bar chart
                                fig1 = px.bar(
                                    df_performance,
                                    x='function_name',
                                    y='execution_time',
                                    title='Average Execution Time by Function (seconds)',
                                    color='execution_time',
                                    color_continuous_scale='Viridis'
                                )
                                fig1.update_layout(xaxis_tickangle=-45)
                                st.plotly_chart(fig1, use_container_width=True)
                            else:
                                st.info("Execution time data not available.")
                        
                        with chart_col2:
                            if 'execution_count' in df_performance.columns:
                                # Execution count bar chart
                                fig2 = px.bar(
                                    df_performance,
                                    x='function_name',
                                    y='execution_count',
                                    title='Execution Count by Function',
                                    color='execution_count',
                                    color_continuous_scale='Viridis'
                                )
                                fig2.update_layout(xaxis_tickangle=-45)
                                st.plotly_chart(fig2, use_container_width=True)
                            else:
                                st.info("Execution count data not available.")
                    else:
                        st.info("Function performance data format is incomplete.")
                except Exception as e:
                    st.warning(f"Error displaying performance charts: {str(e)}")
                    st.info("Performance data is available but couldn't be displayed properly.")
            else:
                st.info("No function performance data available yet.")
            
            # Recent executions
            st.subheader("Recent Executions")
            recent_executions = metrics.get('recent_executions', [])
            if recent_executions and len(recent_executions) > 0:
                try:
                    df_recent = pd.DataFrame(recent_executions)
                    if not df_recent.empty and 'timestamp' in df_recent.columns:
                        df_recent['timestamp'] = pd.to_datetime(df_recent['timestamp'])
                        df_recent['timestamp_local'] = df_recent['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                        if 'success' in df_recent.columns:
                            df_recent['status'] = df_recent['success'].apply(lambda x: '✅ Success' if x else '❌ Failed')
                        else:
                            df_recent['status'] = 'Unknown'
                        
                        columns_to_display = ['timestamp_local']
                        if 'function_name' in df_recent.columns:
                            columns_to_display.append('function_name')
                        columns_to_display.append('status')
                        if 'execution_time' in df_recent.columns:
                            columns_to_display.append('execution_time')
                        if 'runtime' in df_recent.columns:
                            columns_to_display.append('runtime')
                        
                        # Display recent executions in a styled table
                        st.dataframe(
                            df_recent[columns_to_display],
                            column_config={
                                'timestamp_local': 'Timestamp',
                                'function_name': 'Function Name',
                                'status': 'Status',
                                'execution_time': st.column_config.NumberColumn('Execution Time (s)', format="%.3f"),
                                'runtime': 'Runtime'
                            },
                            use_container_width=True
                        )
                    else:
                        st.info("Recent executions data format is incomplete.")
                except Exception as e:
                    st.warning(f"Error displaying recent executions: {str(e)}")
                    st.info("Recent executions data is available but couldn't be displayed properly.")
            else:
                st.info("No recent executions available yet.")
        else:
            st.error(f"Error fetching metrics: {response.text}")
    except Exception as e:
        st.error(f"Error connecting to API: {str(e)}")
        st.exception(e)

# Add some styling
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True) 