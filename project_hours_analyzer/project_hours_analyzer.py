import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from urllib.parse import urlparse

def round_to_quarter_hour(dt):
    """
    Round a datetime to the nearest 15-minute interval.
    
    Args:
        dt (datetime): Input datetime
        
    Returns:
        datetime: Rounded datetime
    """
    # Get minutes and determine which quarter hour to round to
    minutes = dt.minute
    seconds = dt.second
    microseconds = dt.microsecond
    
    # Calculate total minutes including seconds/microseconds
    total_minutes = minutes + seconds/60 + microseconds/60000000
    
    # Round to nearest quarter hour (0, 15, 30, 45)
    quarter_hours = round(total_minutes / 15) * 15
    
    # Handle overflow to next hour
    if quarter_hours >= 60:
        quarter_hours = 0
        dt = dt + timedelta(hours=1)
    
    # Create new datetime with rounded minutes
    rounded_dt = dt.replace(minute=int(quarter_hours), second=0, microsecond=0)
    
    return rounded_dt

def ensure_minimum_session_duration(start_dt, end_dt, min_hours=0.25):
    """
    Ensure a session has a minimum duration by extending the end time if needed.
    
    Args:
        start_dt (datetime): Session start datetime
        end_dt (datetime): Session end datetime  
        min_hours (float): Minimum session duration in hours
        
    Returns:
        tuple: (start_datetime, end_datetime) with minimum duration guaranteed
    """
    duration_hours = (end_dt - start_dt).total_seconds() / 3600
    
    if duration_hours < min_hours:
        # Extend end time to meet minimum duration
        end_dt = start_dt + timedelta(hours=min_hours)
        # Re-round the extended end time to quarter hour
        end_dt = round_to_quarter_hour(end_dt)
    
    return start_dt, end_dt

def extract_project_names(df):
    """
    Extract project names from the dataLink URLs - always the 2nd path segment.
    
    Args:
        df (DataFrame): DataFrame with activity data
        
    Returns:
        dict: Dictionary mapping row indices to project names
    """
    project_mapping = {}
    
    for idx, row in df.iterrows():
        data_link = str(row.get('dataLink', ''))
        
        if data_link and data_link != 'nan':
            try:
                # Parse URL and extract path segments
                # Expected format: https://www.dropbox.com/pri/get/segment1/PROJECT_NAME/rest/of/path
                parsed_url = urlparse(data_link)
                path_segments = [seg for seg in parsed_url.path.split('/') if seg]
                
                # The project name should be the 2nd segment after splitting by '/'
                # Path typically looks like: ['pri', 'get', 'segment1', 'PROJECT_NAME', ...]
                if len(path_segments) >= 4:  # pri/get/segment1/PROJECT_NAME
                    project_name = path_segments[3]  # 4th segment (0-indexed) is the project
                    project_mapping[idx] = project_name
                elif len(path_segments) >= 3:  # Fallback to 3rd segment
                    project_name = path_segments[2]
                    project_mapping[idx] = project_name
                else:
                    project_mapping[idx] = "Unknown_Project"
                    
            except Exception:
                # If URL parsing fails, try simple string splitting
                try:
                    # Split by / and get relevant segment
                    parts = data_link.split('/')
                    if len(parts) > 6:  # Ensure we have enough parts
                        project_name = parts[6]  # Usually the project name position
                        project_mapping[idx] = project_name
                    else:
                        project_mapping[idx] = "Unknown_Project"
                except:
                    project_mapping[idx] = "Unknown_Project"
        else:
            # No dataLink available, try to extract from blurb as fallback
            blurb = str(row.get('blurb', ''))
            if 'In ' in blurb and '[' in blurb:
                # Pattern: "In PROJECT_NAME [URL]"
                try:
                    project_name = blurb.split('In ')[1].split(' [')[0]
                    # Clean up the project name
                    project_name = project_name.strip()
                    # Only use if it's a reasonable length and doesn't contain newlines
                    if project_name and len(project_name) < 100 and '\n' not in project_name:
                        project_mapping[idx] = project_name
                    else:
                        project_mapping[idx] = "Unknown_Project"
                except:
                    project_mapping[idx] = "Unknown_Project"
            else:
                project_mapping[idx] = "Unknown_Project"
    
    return project_mapping

def analyze_all_projects(csv_file_path, time_multiplier=1.0, min_activity_hours=0.25, 
                        max_session_gap_hours=2.0, session_end_buffer=0.25, min_activities=3, 
                        timezone='US/Central'):
    """
    Analyze time spent on all detected projects.
    
    Args:
        csv_file_path (str): Path to the CSV file
        time_multiplier (float): Time estimation multiplier
        min_activity_hours (float): Minimum hours for isolated activities
        max_session_gap_hours (float): Max gap for session grouping
        session_end_buffer (float): Buffer time for session endings
        min_activities (int): Minimum activities required to include a project
        timezone (str): Target timezone for conversion (default: 'US/Central')
        
    Returns:
        tuple: (daily_hours_dict, project_sessions_dict, project_counts)
    """
    
    # Read the CSV file with better error handling
    try:
        # Try reading with different settings to handle problematic lines
        df = pd.read_csv(csv_file_path, on_bad_lines='warn', engine='python')
    except Exception as e:
        print(f"Error reading CSV with python engine: {e}")
        try:
            # Fallback: try with c engine and skip bad lines
            df = pd.read_csv(csv_file_path, on_bad_lines='skip')
            print("Warning: Some malformed lines were skipped")
        except Exception as e2:
            print(f"Error reading CSV: {e2}")
            return {}, {}, {}
    
    # Debug: Print first few rows to understand the data structure
    print("First few rows of data:")
    print(df.head())
    print(f"Columns: {list(df.columns)}")
    print(f"Total rows loaded: {len(df)}")
    
    # Convert timestamp to datetime with better error handling
    df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
    
    # Remove rows where timestamp conversion failed
    df = df.dropna(subset=['timestamp'])
    
    # Convert timestamp - try seconds first, then milliseconds if values are too large
    try:
        # Check if we're dealing with milliseconds (typical for values > 1e12)
        if df['timestamp'].max() > 1e12:
            print("Detected millisecond timestamps")
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            print("Detected second timestamps")  
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # Convert from UTC to specified timezone
        # First localize as UTC, then convert to target timezone
        df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(timezone)
        
        # Remove timezone info for easier processing (but keep the converted time)
        df['datetime'] = df['datetime'].dt.tz_localize(None)
            
        # Debug: Show some converted timestamps
        print(f"\nSample timestamp conversions (converted to {timezone}):")
        for i in range(min(3, len(df))):
            orig_ts = df.iloc[i]['timestamp']
            converted_dt = df.iloc[i]['datetime'] 
            print(f"  {orig_ts} -> {converted_dt}")
            
    except Exception as e:
        print(f"Error converting timestamps: {e}")
        return {}, {}, {}
    
    df['date'] = df['datetime'].dt.date
    
    # Extract project names
    project_mapping = extract_project_names(df)
    df['project'] = df.index.map(project_mapping)
    
    # Count activities per project and filter
    project_counts = Counter(df['project'].values)
    significant_projects = {proj: count for proj, count in project_counts.items() 
                          if count >= min_activities and proj != "Unknown_Project"}
    
    # Calculate hours and sessions for each significant project
    project_hours = {}
    project_sessions = {}
    
    for project_name in significant_projects.keys():
        project_df = df[df['project'] == project_name].copy()
        project_df = project_df.sort_values('datetime')
        
        daily_hours = defaultdict(float)
        sessions = []
        
        # Group by date and calculate hours and sessions
        for date, group in project_df.groupby('date'):
            timestamps = sorted(group['datetime'].tolist())
            
            if len(timestamps) == 1:
                # Single activity - create one session
                start_time = timestamps[0]
                end_time = start_time + timedelta(hours=min_activity_hours * time_multiplier)
                
                # Round times to nearest quarter hour
                rounded_start = round_to_quarter_hour(start_time)
                rounded_end = round_to_quarter_hour(end_time)
                
                # Ensure minimum duration
                rounded_start, rounded_end = ensure_minimum_session_duration(rounded_start, rounded_end)
                
                # Calculate dates (handle potential day overflow)
                start_date = rounded_start.date()
                end_date = rounded_end.date()
                
                # Recalculate hours based on rounded times
                actual_hours = (rounded_end - rounded_start).total_seconds() / 3600
                
                sessions.append({
                    'start_date': start_date,
                    'start_time': rounded_start.time(),
                    'end_date': end_date,
                    'end_time': rounded_end.time(),
                    'hours': round(actual_hours, 2)
                })
                daily_hours[date] = actual_hours
            else:
                # Multiple activities - group into sessions
                current_session_start = timestamps[0]
                current_session_end = timestamps[0]
                daily_session_time = 0
                
                for i in range(1, len(timestamps)):
                    time_diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600
                    
                    if time_diff <= max_session_gap_hours:
                        # Continue current session
                        current_session_end = timestamps[i]
                        daily_session_time += time_diff
                    else:
                        # End current session and start a new one
                        session_duration = daily_session_time + min_activity_hours
                        session_duration *= time_multiplier
                        session_end_time = current_session_start + timedelta(hours=session_duration)
                        
                        # Round session times to nearest quarter hour
                        rounded_start = round_to_quarter_hour(current_session_start)
                        rounded_end = round_to_quarter_hour(session_end_time)
                        
                        # Ensure minimum duration
                        rounded_start, rounded_end = ensure_minimum_session_duration(rounded_start, rounded_end)
                        
                        # Calculate dates (handle potential day overflow)
                        start_date = rounded_start.date()
                        end_date = rounded_end.date()
                        
                        # Recalculate hours based on rounded times
                        actual_hours = (rounded_end - rounded_start).total_seconds() / 3600
                        
                        sessions.append({
                            'start_date': start_date,
                            'start_time': rounded_start.time(),
                            'end_date': end_date,
                            'end_time': rounded_end.time(),
                            'hours': round(actual_hours, 2)
                        })
                        
                        # Start new session
                        current_session_start = timestamps[i]
                        current_session_end = timestamps[i]
                        daily_session_time = min_activity_hours
                
                # Add the final session
                final_session_duration = daily_session_time + session_end_buffer
                final_session_duration *= time_multiplier
                final_session_end = current_session_start + timedelta(hours=final_session_duration)
                
                # Round final session times to nearest quarter hour
                rounded_start = round_to_quarter_hour(current_session_start)
                rounded_end = round_to_quarter_hour(final_session_end)
                
                # Ensure minimum duration
                rounded_start, rounded_end = ensure_minimum_session_duration(rounded_start, rounded_end)
                
                # Calculate dates (handle potential day overflow)
                start_date = rounded_start.date()
                end_date = rounded_end.date()
                
                # Recalculate hours based on rounded times
                actual_hours = (rounded_end - rounded_start).total_seconds() / 3600
                
                sessions.append({
                    'start_date': start_date,
                    'start_time': rounded_start.time(),
                    'end_date': end_date,
                    'end_time': rounded_end.time(),
                    'hours': round(actual_hours, 2)
                })
                
                # Calculate total daily hours
                daily_hours[date] = sum(session['hours'] for session in sessions 
                                     if session['start_date'] == date)
        
        project_hours[project_name] = dict(daily_hours)
        
        # Merge overlapping sessions before storing
        sessions = merge_overlapping_sessions(sessions)
        
        project_sessions[project_name] = sessions
    
    return project_hours, project_sessions, project_counts

def merge_overlapping_sessions(sessions):
    """
    Merge overlapping or adjacent sessions.
    
    Args:
        sessions (list): List of session dictionaries with start/end dates and times
        
    Returns:
        list: Merged sessions with no overlaps
    """
    if not sessions:
        return sessions
    
    # Convert to datetime for easier comparison
    session_intervals = []
    for session in sessions:
        start_dt = datetime.combine(session['start_date'], session['start_time'])
        end_dt = datetime.combine(session['end_date'], session['end_time'])
        session_intervals.append({
            'start_dt': start_dt,
            'end_dt': end_dt,
            'original': session
        })
    
    # Sort by start time
    session_intervals.sort(key=lambda x: x['start_dt'])
    
    # Merge overlapping sessions
    merged = []
    current = session_intervals[0]
    
    for next_session in session_intervals[1:]:
        # Check if sessions overlap or are adjacent (within 15 minutes)
        if next_session['start_dt'] <= current['end_dt'] + timedelta(minutes=15):
            # Merge: extend current session to include next session
            current['end_dt'] = max(current['end_dt'], next_session['end_dt'])
        else:
            # No overlap: save current and move to next
            merged.append(current)
            current = next_session
    
    # Add the last session
    merged.append(current)
    
    # Convert back to session format
    final_sessions = []
    for session in merged:
        # Recalculate hours based on merged times
        actual_hours = (session['end_dt'] - session['start_dt']).total_seconds() / 3600
        
        final_sessions.append({
            'start_date': session['start_dt'].date(),
            'start_time': session['start_dt'].time(),
            'end_date': session['end_dt'].date(),
            'end_time': session['end_dt'].time(),
            'hours': round(actual_hours, 2)
        })
    
    return final_sessions

def calculate_daily_project_hours(csv_file_path, project_name=None, 
                                 time_multiplier=1.0, min_activity_hours=0.25, 
                                 max_session_gap_hours=2.0, session_end_buffer=0.25):
    """
    Calculate daily hours spent on a specific project (legacy function for backward compatibility).
    
    Args:
        csv_file_path (str): Path to the CSV file containing activity data
        project_name (str): Name of specific project to analyze (if None, uses auto-detection)
        time_multiplier (float): Multiplier to adjust overall time estimates (default: 1.0)
        min_activity_hours (float): Minimum hours assigned to isolated activities (default: 0.25)
        max_session_gap_hours (float): Max hours between activities to consider same session (default: 2.0)
        session_end_buffer (float): Hours added to end of each session (default: 0.25)
    
    Returns:
        dict: Dictionary with dates as keys and hours as values
    """
    
    if project_name is None:
        # Use auto-detection and return the largest project
        project_hours, _, _ = analyze_all_projects(csv_file_path, time_multiplier, 
                                              min_activity_hours, max_session_gap_hours, 
                                              session_end_buffer)
        if project_hours:
            # Return the project with the most total hours
            largest_project = max(project_hours.keys(), 
                                key=lambda k: sum(project_hours[k].values()))
            return project_hours[largest_project]
        return {}
    
    # Legacy behavior - search for specific project name
    df = pd.read_csv(csv_file_path)
    df['timestamp'] = pd.to_numeric(df['timestamp'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df['date'] = df['datetime'].dt.date
    
    project_mask = df['blurb'].str.contains(project_name, case=False, na=False)
    project_df = df[project_mask].copy()
    
    if project_df.empty:
        print(f"No activities found for project: {project_name}")
        return {}
    
    project_df = project_df.sort_values('datetime')
    daily_hours = defaultdict(float)
    
    for date, group in project_df.groupby('date'):
        timestamps = sorted(group['datetime'].tolist())
        
        if len(timestamps) == 1:
            daily_hours[date] = min_activity_hours * time_multiplier
        else:
            total_session_time = 0
            
            for i in range(1, len(timestamps)):
                time_diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600
                
                if time_diff <= max_session_gap_hours:
                    total_session_time += time_diff
                else:
                    total_session_time += min_activity_hours
            
            total_session_time += session_end_buffer
            total_session_time *= time_multiplier
            daily_hours[date] = round(total_session_time, 2)
    
    return dict(daily_hours)

def print_daily_summary(daily_hours):
    """Print a formatted summary of daily hours."""
    if not daily_hours:
        print("No project hours found.")
        return
    
    print("\n=== Daily Project Hours Summary ===")
    print(f"{'Date':<12} {'Hours':<8} {'Visual'}")
    print("-" * 35)
    
    total_hours = 0
    for date, hours in sorted(daily_hours.items()):
        total_hours += hours
        # Create visual bar (each # = 0.5 hours)
        bar_length = int(hours * 2)
        visual_bar = "#" * bar_length
        print(f"{date} {hours:>6.2f}h   {visual_bar}")
    
    print("-" * 35)
    print(f"Total: {total_hours:.2f} hours across {len(daily_hours)} days")
    print(f"Average: {total_hours/len(daily_hours):.2f} hours per active day")

def analyze_work_patterns(daily_hours):
    """Analyze work patterns from the daily hours data."""
    if not daily_hours:
        return
    
    hours_list = list(daily_hours.values())
    dates_list = list(daily_hours.keys())
    
    print("\n=== Work Pattern Analysis ===")
    print(f"Most productive day: {max(daily_hours, key=daily_hours.get)} ({max(hours_list):.2f}h)")
    print(f"Least productive day: {min(daily_hours, key=daily_hours.get)} ({min(hours_list):.2f}h)")
    
    # Find streaks of consecutive days
    sorted_dates = sorted(dates_list)
    current_streak = 1
    max_streak = 1
    
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i-1]).days == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1
    
    print(f"Longest work streak: {max_streak} consecutive days")

def sanitize_filename(filename):
    """
    Sanitize a string to be used as a filename.
    
    Args:
        filename (str): Original filename
        
    Returns:
        str: Sanitized filename safe for all operating systems
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*\n\r\t'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Replace multiple underscores with single underscore
    while '__' in filename:
        filename = filename.replace('__', '_')
    
    # Remove leading/trailing underscores and spaces
    filename = filename.strip('_ ')
    
    # Limit length to 200 characters (leaving room for prefix/suffix)
    if len(filename) > 200:
        filename = filename[:200]
    
    # If filename is empty or only special chars, use a default
    if not filename or filename == '_':
        filename = "Unknown_Project"
    
    return filename

def export_to_csv(project_sessions, output_file="project_sessions.csv"):
    """Export the project sessions to a CSV file with Start Date, Start Time, End Date, End Time, Hours columns."""
    if not project_sessions:
        print("No session data to export.")
        return
    
    df_export = pd.DataFrame([
        {
            "start_date": session['start_date'],
            "start_time": session['start_time'].strftime('%H:%M:%S'),
            "end_date": session['end_date'],
            "end_time": session['end_time'].strftime('%H:%M:%S'),
            "hours": session['hours']
        }
        for session in project_sessions
    ])
    
    # Sort by start date and time
    df_export['start_datetime'] = pd.to_datetime(
        df_export['start_date'].astype(str) + ' ' + df_export['start_time']
    )
    df_export = df_export.sort_values('start_datetime')
    df_export = df_export.drop('start_datetime', axis=1)  # Remove helper column
    
    df_export.to_csv(output_file, index=False)
    print(f"Session data exported to: {output_file}")

def export_daily_summary_to_csv(daily_hours, output_file="daily_project_hours.csv"):
    """Export the daily hours summary to a CSV file (legacy function)."""
    if not daily_hours:
        print("No data to export.")
        return
    
    df_export = pd.DataFrame([
        {"date": date, "hours": hours} 
        for date, hours in sorted(daily_hours.items())
    ])
    
    df_export.to_csv(output_file, index=False)
    print(f"Daily summary exported to: {output_file}")

def print_project_summary(project_hours, project_counts):
    """Print summary of all detected projects."""
    
    if not project_hours:
        print("No significant projects found in the data.")
        return
    
    print("\n=== Multi-Project Time Analysis ===")
    print(f"Found {len(project_hours)} significant projects:")
    print()
    
    # Calculate totals for ranking
    project_totals = {}
    for project, daily_hours in project_hours.items():
        total_hours = sum(daily_hours.values()) if daily_hours else 0
        active_days = len(daily_hours)
        avg_hours = total_hours / active_days if active_days > 0 else 0
        project_totals[project] = {
            'total_hours': total_hours,
            'active_days': active_days,
            'avg_hours': avg_hours,
            'activity_count': project_counts[project]
        }
    
    # Sort by total hours (most time spent first)
    sorted_projects = sorted(project_totals.items(), 
                           key=lambda x: x[1]['total_hours'], reverse=True)
    
    # Print overview table
    print(f"{'Project':<25} {'Total Hours':<12} {'Days':<6} {'Avg/Day':<8} {'Activities'}")
    print("-" * 70)
    
    for project, stats in sorted_projects:
        print(f"{project:<25} {stats['total_hours']:<12.1f} "
              f"{stats['active_days']:<6} {stats['avg_hours']:<8.1f} "
              f"{stats['activity_count']}")
    
    print("-" * 70)
    total_all_hours = sum(stats['total_hours'] for _, stats in sorted_projects)
    print(f"{'TOTAL':<25} {total_all_hours:<12.1f}")
    
    # Print detailed breakdown for each project
    for project, daily_hours in project_hours.items():
        if daily_hours:  # Only show projects with calculated hours
            print(f"\n--- {project} ---")
            print(f"{'Date':<12} {'Hours':<8} {'Visual'}")
            print("-" * 30)
            
            for date, hours in sorted(daily_hours.items()):
                bar_length = int(hours * 2)
                visual_bar = "#" * bar_length
                print(f"{date} {hours:>6.2f}h   {visual_bar}")

def detect_and_analyze_projects(csv_file_path, **kwargs):
    """
    Main function to detect projects and analyze time spent on each.
    """
    try:
        project_hours, project_sessions, project_counts = analyze_all_projects(csv_file_path, **kwargs)
        
        print("=== Project Detection Results ===")
        print(f"Total activities processed: {sum(project_counts.values())}")
        print(f"Projects detected: {len(project_counts)}")
        
        # Show all detected projects (including small ones)
        print(f"\nAll detected projects (activity count):")
        for project, count in sorted(project_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {project}: {count} activities")
        
        # Show detailed analysis for significant projects
        print_project_summary(project_hours, project_counts)
        
        return project_hours, project_sessions, project_counts
        
    except Exception as e:
        print(f"Error analyzing projects: {e}")
        return {}, {}, {}

def analyze_specific_project(csv_file_path, project_name, **kwargs):
    """Analyze a specific project by name."""
    daily_hours = calculate_daily_project_hours(csv_file_path, project_name, **kwargs)
    if daily_hours:
        print(f"\n=== {project_name} Analysis ===")
        print_daily_summary(daily_hours)
        analyze_work_patterns(daily_hours)
    else:
        print(f"No data found for project: {project_name}")
    return daily_hours

def calculate_hours_from_text_data(text_data, project_name="Bonsai_Tutorials",
                                 time_multiplier=1.0, min_activity_hours=0.25,
                                 max_session_gap_hours=2.0, session_end_buffer=0.25):
    """
    Calculate hours from raw text data instead of CSV file.
    
    Args:
        text_data (str): Raw text data with timestamp and activity info
        project_name (str): Project name to filter for
        time_multiplier (float): Multiplier to adjust overall time estimates
        min_activity_hours (float): Minimum hours for isolated activities
        max_session_gap_hours (float): Max hours between activities for same session
        session_end_buffer (float): Hours added to end of each session
    """
    lines = text_data.strip().split('\n')
    activities = []
    
    for line in lines[1:]:  # Skip header
        parts = line.split('\t')
        if len(parts) >= 3:
            try:
                timestamp = int(parts[1])
                blurb = parts[4] if len(parts) > 4 else ""
                if project_name.lower() in blurb.lower():
                    activities.append({
                        'timestamp': timestamp,
                        'datetime': datetime.fromtimestamp(timestamp),
                        'blurb': blurb
                    })
            except (ValueError, IndexError):
                continue
    
    if not activities:
        return {}
    
    # Group by date and calculate hours
    daily_activities = defaultdict(list)
    
    for activity in activities:
        date = activity['datetime'].date()
        daily_activities[date].append(activity['datetime'])
    
    daily_hours = {}
    for date, timestamps in daily_activities.items():
        timestamps.sort()
        if len(timestamps) == 1:
            daily_hours[date] = min_activity_hours * time_multiplier
        else:
            total_time = 0
            for i in range(1, len(timestamps)):
                diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600
                if diff <= max_session_gap_hours:  # Within session gap = same session
                    total_time += diff
                else:
                    total_time += min_activity_hours  # Add minimum for isolated activity
            total_time += session_end_buffer  # Add buffer for last activity
            total_time *= time_multiplier  # Apply multiplier
            daily_hours[date] = round(total_time, 2)
    
    return daily_hours

def parse_activity_data_from_text(text_data):
    """
    Parse activity data from the raw text format you provided.
    
    Args:
        text_data (str): Raw activity text data
        
    Returns:
        DataFrame: Parsed activity data
    """
    lines = text_data.strip().split('\n')
    activities = []
    
    for line in lines:
        if not line.strip():
            continue
            
        # Parse the line format: Name Timestamp Date Time AM/PM Description... URL
        parts = line.split()
        if len(parts) < 6:
            continue
            
        try:
            # Extract name (first two parts usually)
            name = f"{parts[0]} {parts[1]}"
            
            # Extract timestamp (3rd part)  
            timestamp = int(parts[2])
            
            # Extract date and time (4th, 5th, 6th parts)
            date_str = parts[3]  # e.g., "7/29/2025" 
            time_str = f"{parts[4]} {parts[5]}"  # e.g., "7:44 AM"
            
            # Find the dataLink URL (usually starts with https://www.dropbox.com)
            datalink = ""
            blurb = ""
            
            # Join the rest and split to find URL and description
            rest_of_line = " ".join(parts[6:])
            
            # Look for dropbox URL
            if "https://www.dropbox.com" in rest_of_line:
                url_start = rest_of_line.find("https://www.dropbox.com")
                datalink = rest_of_line[url_start:].split()[0]  # Get first URL
                blurb = rest_of_line[:url_start].strip()
            else:
                blurb = rest_of_line
            
            activities.append({
                'name': name,
                'timestamp': timestamp,
                'date_str': date_str,
                'time_str': time_str, 
                'blurb': blurb,
                'dataLink': datalink
            })
            
        except (ValueError, IndexError) as e:
            print(f"Error parsing line: {line[:100]}... Error: {e}")
            continue
    
    # Convert to DataFrame
    df = pd.DataFrame(activities)
    
    # Parse the human-readable date/time to verify against timestamp
    if not df.empty:
        try:
            df['parsed_datetime'] = pd.to_datetime(df['date_str'] + ' ' + df['time_str'])
            print("Sample parsed times vs timestamps:")
            for i in range(min(3, len(df))):
                ts = df.iloc[i]['timestamp']
                parsed_dt = df.iloc[i]['parsed_datetime']
                ts_dt = pd.to_datetime(ts, unit='s')
                print(f"  Parsed: {parsed_dt} | Timestamp: {ts_dt} | Raw: {ts}")
        except Exception as e:
            print(f"Error parsing human dates: {e}")
    
    return df

# Test function for your specific data
def test_with_sample_data():
    """Test the parsing with your sample data"""
    sample_data = """Ryan Schultz 1753793408 7/29/2025 7:50 AM You added <a target='_blank' href='/event_details/7117445/11079406/1114517657/0'>3499 files</a> You added 3499 files [/event_details/7117445/11079406/1114517657/0]. https://www.dropbox.com/pri/get/Gitea_OD/Restaurant_Brookfield_3/.git/hooks/push-to-checkout.sample?_subject_uid=7117445&source=event_details&w=AAAwItLcdibhIWcu7F_cqa0GCA0TH-tUP9vFhOfxR75U0g
Ryan Schultz 1753793408 7/29/2025 7:50 AM You edited <a target='_blank' href='/event_details/7117445/11079406/1114517657/0'>24 files</a> You edited 24 files [/event_details/7117445/11079406/1114517657/0]. https://www.dropbox.com/pri/get/Gitea_OD/Restaurant_Brookfield_3/.git/hooks/push-to-checkout.sample?_subject_uid=7117445&source=event_details&w=AAAwItLcdibhIWcu7F_cqa0GCA0TH-tUP9vFhOfxR75U0g
Ryan Schultz 1753793081 7/29/2025 7:44 AM You edited <a target='_blank' href='/event_details/7117445/12129600851/1114517815/0'>House.ifc and 8 more files</a> In Bonsai_Tutorials [https://www.dropbox.com/home/Gitea_OD/Bonsai_Tutorials], you edited House.ifc and 8 more files [/event_details/7117445/12129600851/1114517815/0]. https://www.dropbox.com/pri/get/Gitea_OD/Bonsai_Tutorials/_Model/Animation/Animation%20for%20Model/temp.png1129.png?_subject_uid=7117445&source=event_details&w=AAAvRROpPeoPko63KcaiT8a98nQNsw-X9_c3qBoY8vV2VQ"""
    
    print("Testing sample data parsing...")
    df = parse_activity_data_from_text(sample_data)
    print(f"Parsed {len(df)} activities")
    return df

# Example usage with automatic project detection
if __name__ == "__main__":
    # Replace with your actual CSV file path
    csv_file = "activity_data.csv"
    
    # Uncomment the line below to test with sample data first
    # test_with_sample_data()
    
    # Time estimation presets
    ESTIMATION_PRESETS = {
        "conservative": {
            "time_multiplier": 0.75,
            "min_activity_hours": 0.15,
            "max_session_gap_hours": 1.5,
            "session_end_buffer": 0.15
        },
        "moderate": {
            "time_multiplier": 1.0,
            "min_activity_hours": 0.25,
            "max_session_gap_hours": 2.0,
            "session_end_buffer": 0.25
        },
        "generous": {
            "time_multiplier": 1.5,
            "min_activity_hours": 0.5,
            "max_session_gap_hours": 3.0,
            "session_end_buffer": 0.5
        }
    }
    
    # Choose your estimation level
    estimation_level = "moderate"  # Change to: conservative, moderate, or generous
    settings = ESTIMATION_PRESETS[estimation_level]
    
    try:
        print(f"Analyzing all projects with '{estimation_level}' time estimation...")
        print(f"Settings: {settings}")
        
        # Auto-detect and analyze all projects
        project_hours, project_sessions, project_counts = detect_and_analyze_projects(csv_file, **settings)
        
        # Export each project's session data
        for project_name, sessions in project_sessions.items():
            if sessions:
                safe_name = sanitize_filename(project_name)
                filename = f"sessions_{safe_name}_{estimation_level}.csv"
                export_to_csv(sessions, filename)
        
        print(f"\nSession data exported for {len(project_sessions)} projects")
        
    except FileNotFoundError:
        print(f"CSV file '{csv_file}' not found. Please check the file path.")
    except Exception as e:
        print(f"Error processing data: {e}")