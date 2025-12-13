import streamlit as st
import os

def load_custom_css():
    """
    Loads and injects the custom CSS from src/styles/custom.css
    """
    # Go up two levels from utils/ui.py -> src/ -> then to styles/custom.css
    # But simpler: use absolute path relative to project root or relative to this file
    
    # This file is in src/utils/ui.py
    # custom.css is in src/styles/custom.css
    current_dir = os.path.dirname(os.path.abspath(__file__)) # src/utils
    project_root = os.path.dirname(os.path.dirname(current_dir)) # Project Root
    css_path = os.path.join(project_root, 'src', 'styles', 'custom.css')

    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        # Fallback or logging if needed
        pass
