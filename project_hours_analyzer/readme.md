# Project Hours Analyzer

A Python tool for analyzing time spent on projects from Dropbox activity data.

## CSV File Format Requirements

Your input CSV file must have the following columns:

```csv
name,timestamp,date,time,blurb,dataLink
Ryan Schultz,1753793081,7/29/2025,7:44 AM,You edited House.ifc and 8 more files,https://www.dropbox.com/pri/get/Gitea_OD/Bonsai_Tutorials/House.ifc
```

### Required Columns:

1. **name** - User name (e.g., "Ryan Schultz")
2. **timestamp** - Unix timestamp in seconds (e.g., 1753793081)
3. **date** - Human-readable date (e.g., "7/29/2025") - for reference only
4. **time** - Human-readable time (e.g., "7:44 AM") - for reference only
5. **blurb** - Activity description containing project information
6. **dataLink** - Full Dropbox URL to the file/folder

### Important Notes:

- **Timestamps are in UTC** - The script will convert them to your local timezone (default: US/Central)
- **Project names** are extracted from the `dataLink` URL path (4th segment after domain)
- If no dataLink is available, the script tries to extract project name from the `blurb` field
- Activities with fewer than 3 occurrences are filtered out by default

### Example CSV Structure:

| name          | timestamp  | date       | time    | blurb                                    | dataLink                                                                                                    |
|---------------|------------|------------|---------|------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| Ryan Schultz  | 1753793408 | 7/29/2025  | 7:50 AM | You added 3499 files                     | https://www.dropbox.com/pri/get/Gitea_OD/Restaurant_Brookfield_3/.git/hooks/push-to-checkout.sample       |
| Ryan Schultz  | 1753793408 | 7/29/2025  | 7:50 AM | You edited 24 files                      | https://www.dropbox.com/pri/get/Gitea_OD/Restaurant_Brookfield_3/.git/config                              |
| Ryan Schultz  | 1753793081 | 7/29/2025  | 7:44 AM | In Bonsai_Tutorials you edited House.ifc | https://www.dropbox.com/pri/get/Gitea_OD/Bonsai_Tutorials/_Model/House.ifc                                |

## Prerequisites

```bash
# Install required dependencies
pip install pandas numpy
```

## Command Line Usage

### Basic usage (analyzes all projects automatically):

```bash
python project_hours_analyzer.py
```

This will:
- Detect all projects from your activity data
- Use moderate time estimation settings
- Convert timestamps from UTC to US/Central timezone
- Export CSV files for each project found

### Custom timezone (if you're not in Central Time):

```bash
python -c "
import project_hours_analyzer as pha
project_hours, sessions, counts = pha.detect_and_analyze_projects(
    'activity_data.csv', 
    timezone='US/Eastern'  # or 'US/Pacific', 'US/Mountain', etc.
)
"
```

### Analyze with conservative time estimates:

```bash
python -c "
import project_hours_analyzer as pha
project_hours, sessions, counts = pha.detect_and_analyze_projects(
    'activity_data.csv', 
    time_multiplier=0.75, 
    min_activity_hours=0.15, 
    max_session_gap_hours=1.5,
    timezone='US/Central'
)
"
```

### Analyze with generous time estimates:

```bash
python -c "
import project_hours_analyzer as pha
project_hours, sessions, counts = pha.detect_and_analyze_projects(
    'activity_data.csv', 
    time_multiplier=1.5, 
    min_activity_hours=0.5, 
    max_session_gap_hours=3.0
)
"
```

### Analyze a specific project only:

```bash
python -c "
import project_hours_analyzer as pha
daily_hours = pha.analyze_specific_project(
    'activity_data.csv', 
    'Restaurant_Brookfield_3', 
    time_multiplier=1.1
)
"
```

### Custom filename and settings:

```bash
python -c "
import project_hours_analyzer as pha
project_hours, sessions, counts = pha.detect_and_analyze_projects(
    'my_dropbox_data.csv', 
    time_multiplier=1.3, 
    min_activities=5,
    timezone='US/Pacific'
)
"
```

### Interactive mode for experimentation:

```bash
python -i project_hours_analyzer.py
```

Then in the Python shell:

```python
# Try different settings
project_hours, sessions, counts = detect_and_analyze_projects(
    'activity_data.csv', 
    time_multiplier=0.9,
    timezone='US/Central'
)

# Analyze specific project
analyze_specific_project('activity_data.csv', 'Bonsai_Tutorials')

# Export specific project sessions
export_to_csv(sessions['Bonsai_Tutorials'], 'bonsai_sessions.csv')
```

## Configuration Options

### Time Estimation Presets

The script includes three built-in presets:

**Conservative** (underestimates time):
```python
{
    "time_multiplier": 0.75,
    "min_activity_hours": 0.15,
    "max_session_gap_hours": 1.5,
    "session_end_buffer": 0.15
}
```

**Moderate** (balanced, default):
```python
{
    "time_multiplier": 1.0,
    "min_activity_hours": 0.25,
    "max_session_gap_hours": 2.0,
    "session_end_buffer": 0.25
}
```

**Generous** (overestimates time):
```python
{
    "time_multiplier": 1.5,
    "min_activity_hours": 0.5,
    "max_session_gap_hours": 3.0,
    "session_end_buffer": 0.5
}
```

### Parameters Explained

- **time_multiplier**: Overall multiplier for all time estimates (1.0 = no adjustment)
- **min_activity_hours**: Minimum time assigned to isolated activities (default: 0.25 hours = 15 minutes)
- **max_session_gap_hours**: Maximum gap between activities to consider them part of the same session (default: 2.0 hours)
- **session_end_buffer**: Extra time added at the end of each session (default: 0.25 hours)
- **min_activities**: Minimum number of activities required to include a project in analysis (default: 3)
- **timezone**: Target timezone for timestamp conversion (default: 'US/Central')

### Available Timezones

- `'US/Eastern'` or `'America/New_York'`
- `'US/Central'` or `'America/Chicago'`
- `'US/Mountain'` or `'America/Denver'`
- `'US/Pacific'` or `'America/Los_Angeles'`
- `'UTC'` - Coordinated Universal Time
- Or any valid IANA timezone name

## Output Files

### Session CSV Format

The script generates CSV files with the following columns:

```csv
start_date,start_time,end_date,end_time,hours
2025-07-29,07:45:00,2025-07-29,08:00:00,0.25
2025-07-29,18:45:00,2025-07-29,20:45:00,2.0
2025-07-30,17:30:00,2025-07-30,17:45:00,0.25
```

- **start_date**: Date when the session started (YYYY-MM-DD)
- **start_time**: Time when the session started (HH:MM:SS in local timezone)
- **end_date**: Date when the session ended (may differ if session crosses midnight)
- **end_time**: Time when the session ended (HH:MM:SS in local timezone)
- **hours**: Total duration of the session in decimal hours

### File Naming Convention

Output files are named using the pattern:
```
sessions_{PROJECT_NAME}_{ESTIMATION_LEVEL}.csv
```

Examples:
- `sessions_Restaurant_Brookfield_3_moderate.csv`
- `sessions_Bonsai_Tutorials_moderate.csv`
- `sessions_IfcOpenShell_conservative.csv`

## Expected File Structure

```
your_folder/
├── project_hours_analyzer.py
├── activity_data.csv              (your input file)
└── output files created by script:
    ├── sessions_Restaurant_Brookfield_3_moderate.csv
    ├── sessions_Bonsai_Tutorials_moderate.csv
    └── sessions_IfcOpenShell_moderate.csv
```

## Key Features

✅ **Automatic Project Detection** - Extracts project names from Dropbox URLs  
✅ **Timezone Conversion** - Converts UTC timestamps to your local time  
✅ **Session Merging** - Automatically merges overlapping sessions  
✅ **Quarter-Hour Rounding** - All times rounded to 15-minute intervals  
✅ **Minimum Duration** - Ensures all sessions meet minimum duration (default: 15 minutes)  
✅ **Multiple Projects** - Analyzes all projects in one run  
✅ **Flexible Time Estimation** - Three presets plus custom settings  

## Troubleshooting

### Times are showing wrong timezone
Make sure to set the `timezone` parameter:
```python
detect_and_analyze_projects('activity_data.csv', timezone='US/Eastern')
```

### Project not detected
- Check that the project has at least 3 activities (change with `min_activities` parameter)
- Verify the `dataLink` URLs contain the project name in the correct path position
- Try using `print(project_counts)` to see all detected projects

### Overlapping sessions
The script automatically merges overlapping sessions. If you still see overlaps, the sessions may be from different days or have a gap larger than 15 minutes.

## Example Workflow

1. Export your Dropbox activity data to CSV with the required columns
2. Place the CSV in the same folder as the script
3. Run: `python project_hours_analyzer.py`
4. Review the console output showing detected projects and total hours
5. Check the generated CSV files for detailed session breakdowns
6. Import the session CSVs into your time tracking or invoicing software

## Support

For issues or questions about CSV formatting, check the example format above or examine the sample data in the `test_with_sample_data()` function within the script.