import json
import html

# GitHub-like dark theme colors derived from theme.py
COLORS = {
    "DEBUG": "#8b949e",    # Gray (MutedLabel)
    "INFO": "#c9d1d9",     # White (Default text)
    "WARNING": "#d29922",  # Gold (DirtyLabel)
    "ERROR": "#f85149",    # Red (Alert)
    "TIMESTAMP": "#58a6ff" # Blue (Focus/Links)
}

# Keys that are considered "noisy" geometry/telemetry data
# These will be dimmed to improve readability of the main message.
NOISY_KEYS = {
    "host_width", "host_height", "hint_width", "hint_height", 
    "child_count", "item_count", "visible", 
    "tags_wrap_width", "tags_wrap_height", "tags_wrap_hint_width", "tags_wrap_hint_height", 
    "wd_panel_width", "wd_panel_height", "total_width", "total_height"
}

def render_log_html(lines: list[str], show_debug: bool = True, mode: str = "Normal") -> str:
    """
    Renders a list of JSONL log lines into an HTML string for display in QPlainTextEdit or similar.
    """
    html_lines = []
    
    # CSS for the log entries
    header = "<style>pre { white-space: pre-wrap; margin: 0; font-family: 'Segoe UI', monospace; font-size: 9pt; }</style>"
    html_lines.append(header)

    for line in lines:
        if not line.strip():
            continue
            
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            # Fallback for non-JSON lines (e.g. startup headers)
            html_lines.append(f"<div style='color: #8b949e; font-style: italic;'>{html.escape(line)}</div>")
            continue

        level = str(item.get("level", "INFO")).upper()
        
        # Filtering
        if not show_debug and level == "DEBUG":
            continue

        if mode == "Full":
            # Pretty-print the whole JSON blob
            color = COLORS.get(level, COLORS["INFO"])
            safe_json = html.escape(json.dumps(item, indent=2))
            html_lines.append(f"<div style='color: {color}; margin-bottom: 16px;'><pre>{safe_json}</pre></div>")
            continue

        # Normal Mode: Semantic layout
        timestamp = str(item.get("timestamp", ""))[-8:]
        message = item.get("message", "")
        color = COLORS.get(level, COLORS["INFO"])
        ts_color = COLORS["TIMESTAMP"]

        # Main line
        main_line = (
            f"<span style='color: {ts_color};'>{timestamp}</span>  "
            f"<b style='color: {color};'>{level:<7}</b> "
            f"<span style='color: {color};'>{html.escape(message)}</span>"
        )
        
        # Details (all keys except the core ones)
        details = []
        error_details = []
        skip = {"timestamp", "level", "module", "message"}
        
        for key, value in item.items():
            if key in skip:
                continue
            
            # Format value
            if isinstance(value, str) and len(value) > 200:
                value = f"{value[:197]}..."
            
            val_str = html.escape(str(value))
            
            # Specialized parsing for errors/exceptions
            if key.lower() in {"error", "exception", "traceback"}:
                error_details.append(f"<div style='color: #ff7b72; background: #21262d; padding: 4px; border-radius: 4px; margin-top: 4px;'><pre>{val_str}</pre></div>")
                continue

            if key in NOISY_KEYS:
                # Dim the geometry/telemetry keys
                details.append(f"<span style='color: #484f58;'>{key}=</span><span style='color: #8b949e;'>{val_str}</span>")
            else:
                details.append(f"<span style='color: #8b949e;'>{key}=</span><span style='color: #c9d1d9;'>{val_str}</span>")

        entry_html = f"<div style='margin-bottom: 12px;'>{main_line}"
        if details:
            entry_html += f"<div style='margin-left: 65px; font-size: 8pt; line-height: 1.5; color: #8b949e;'>{' | '.join(details)}</div>"
        if error_details:
            entry_html += f"<div style='margin-left: 65px;'>{''.join(error_details)}</div>"
        entry_html += "</div>"
        
        html_lines.append(entry_html)

    return "".join(html_lines)
