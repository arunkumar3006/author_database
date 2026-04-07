import streamlit as st
import pandas as pd
import os
import asyncio
import base64
from datetime import datetime
from types import SimpleNamespace
from loguru import logger
import io

from main import ScraperOrchestrator
from token_manager import TokenManager
from config import INPUT_FILE, OUTPUT_FILE, MAX_DAILY_REQUESTS

# ==========================================
# PAGE CONFIG & PREMIUM CSS
# ==========================================
st.set_page_config(
    page_title="Mavericks Intelligence Dashboard",
    page_icon="🖋️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def local_css():
    st.markdown("""
    <style>
    /* Premium Background & Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    }

    /* Glass Panels */
    div.stButton > button {
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        border: none;
        padding: 0.6rem 2rem;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        width: 100%;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
        background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%);
    }

    .main-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 2rem;
        margin-bottom: 2rem;
    }
    
    h1, h2, h3 {
        color: #f8fafc !important;
        font-weight: 800 !important;
    }
    
    .status-text {
        color: #94a3b8;
        font-size: 0.9rem;
    }
    
    /* Custom Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0f172a;
    }
    ::-webkit-scrollbar-thumb {
        background: #334155;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

local_css()

# ==========================================
# CUSTOM STREAMLIT LOGGER
# ==========================================
class StreamlitLogHandler:
    def __init__(self):
        self.logs = []
    
    def write(self, message):
        if message.strip():
            self.logs.append(message.strip())
            # Keep only last 50 logs
            if len(self.logs) > 50:
                self.logs.pop(0)

# ==========================================
# APP LOGIC
# ==========================================
def main():
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/feather.png", width=60)
        st.title("Mavericks Intelligence")
        st.markdown("---")
        
        # Token Info
        valid, token_info = TokenManager.check_expiry()
        if valid:
            st.success(f"✅ Token Active\n\nExpires: {token_info.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.error(f"❌ Token Status\n\n{token_info}")
            if st.button("Refresh Token Info"):
                st.rerun()

    # Header
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.title("Journalist Data Enrichment")
    st.markdown('<p class="status-text">Premium Mavericks API Automation Engine</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader("Upload Journalist List (Excel)", type=["xlsx"])
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        limit = st.number_input("Max Journalists", min_value=1, max_value=200, value=20)
        resume = st.checkbox("Resume from Checkpoint", value=True)
        dry_run = st.checkbox("Dry Run (Fast)", value=False)
        refresh_outlets = st.checkbox("Refresh Outlet Cache", value=False, help="Forces API fetch for the latest publication IDs")

    if uploaded_file is not None:
        # Save to input folder
        os.makedirs("input", exist_ok=True)
        with open("input/journalists.xlsx", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        st.info(f"📁 Loaded {uploaded_file.name}. Ready to process.")

        # Controls
        if st.button("🚀 START ENRICHMENT"):
            run_scraper(limit, resume, dry_run, refresh_outlets)

    st.markdown('</div>', unsafe_allow_html=True)

def run_scraper(limit, resume, dry_run, refresh_outlets):
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_area = st.empty()
    
    # Custom Args Namespace
    args = SimpleNamespace(
        input="input/journalists.xlsx",
        output="output/journalists_enriched.xlsx",
        resume=resume,
        limit=limit,
        dry_run=dry_run,
        check_token=False,
        refresh_outlets=refresh_outlets
    )

    # Logging capture
    log_handler = StreamlitLogHandler()
    logger.remove()
    logger.add(log_handler.write, level="INFO")
    
    async def execute():
        orchestrator = ScraperOrchestrator(args)
        
        # Startup checks copied from main.py for UI feedback
        valid, token_info = TokenManager.check_expiry()
        if not valid:
            st.error(token_info)
            return

        # Load input for preview/progress
        try:
            df, name_col, pub_col = orchestrator.excel.read_input(args.input)
        except Exception as e:
            st.error(f"Failed to load Excel: {e}")
            return

        if df.empty:
            st.error("Input file is empty.")
            return

        # Simple manual override for display only
        to_process = [idx for idx in df.index if not (resume and str(idx) in orchestrator.checkpoint)]
        if limit:
            to_process = to_process[:limit]
        
        total = len(to_process)
        if total == 0:
            st.success("No new journalists to process!")
            return

        # We'll need to run the orchestrator loop but we want progress
        # So we can provide a small callback interface to Orchestrator or just 
        # replicate parts of the loop for Streamlit visibility
        
        # Override the orchestrator's logger to use ours
        orchestrator.logger = logger
        
        # Start
        st.toast("Initialization complete. Starting scraper...")
        
        # Background task for orchestrator.run() would be cleaner, but we'll 
        # try to capture status updates here inside the execute loop
        
        # This is a bit of a hack to get live updates without changing main.py too much
        # Ideally, main.py ScraperOrchestrator should emit events.
        # For now, we will just run it and show the logs.
        
        with st.spinner("Processing Mavericks API calls..."):
            # Redirect stdout to capture the print() statements from main.py
            class StdoutCapture:
                def __init__(self, placeholder):
                    self.placeholder = placeholder
                def write(self, s):
                    if s.strip():
                        self.placeholder.markdown(f"**Current Task:** `{s.strip()}`")
                def flush(self): pass

            # Run the orchestrator
            await orchestrator.run()

        st.success("Enrichment Complete!")
        
        # Download link
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "rb") as f:
                btn = st.download_button(
                    label="📥 Download Enriched Results",
                    data=f,
                    file_name="journalists_enriched.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    # Log display loop
    async def update_ui():
        while True:
            log_area.code("\n".join(log_handler.logs[-15:]), language="text")
            await asyncio.sleep(0.5)

    # Run composite task
    try:
        # Use existing loop if available (Streamlit may have one)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            # If running in a loop, we can't use run(), so we use a task
            asyncio.create_task(execute())
        else:
            loop.run_until_complete(execute())
            
    except Exception as e:
        logger.exception(e)
        st.error(f"Unexpected Error: {e}")

if __name__ == "__main__":
    main()
