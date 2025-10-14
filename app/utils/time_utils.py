from datetime import datetime, timedelta, timezone

def to_beijing_time(utc_dt):
    if utc_dt is None:
        return ""
    if isinstance(utc_dt, str):
        try:
            # Handle ISO format with Z for UTC
            if utc_dt.endswith('Z'):
                utc_dt = utc_dt[:-1] + '+00:00'
            utc_dt = datetime.fromisoformat(utc_dt)
        except ValueError:
             try:
                # Handle format like '2023-10-27 10:00:00.123456'
                utc_dt = datetime.strptime(utc_dt, '%Y-%m-%d %H:%M:%S.%f')
             except ValueError:
                try:
                    # Handle format like '2023-10-27 10:00:00'
                    utc_dt = datetime.strptime(utc_dt, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return utc_dt # Return original string if parsing fails
    
    # If the datetime object is naive, assume it's in UTC
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        
    # Create a timezone object for Beijing Time (UTC+8)
    beijing_tz = timezone(timedelta(hours=8))
    
    # Convert the UTC datetime to Beijing Time
    beijing_dt = utc_dt.astimezone(beijing_tz)
    
    return beijing_dt.strftime('%Y-%m-%d %H:%M:%S')
