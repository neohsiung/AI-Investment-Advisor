"""
   2026 SaaS Component Library for Streamlit
   Reusable UI elements for a professional Investment Advisor experience.
"""
import re
import streamlit as st
from src.utils.ui import safe_html

def load_material_font():
    """Inject Google Material Symbols font (once per session)."""
    if "material_font_loaded" not in st.session_state:
        safe_html('<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet">')
        st.session_state["material_font_loaded"] = True

def _resolve_icon(icon: str) -> str:
    """Convert :material/icon_name: shortcode to Material Symbols HTML span, or return emoji as-is."""
    if not icon:
        return ""
    m = re.match(r'^:material/(\w+):$', icon)
    if m:
        return f'<span class="material-symbols-outlined" style="font-size: 1.1rem; vertical-align: middle;">{m.group(1)}</span>'
    return icon

def saas_card_start(title=None, subtitle=None, icon=None):
    """Start a SaaS-styled card container."""
    html = f"""<div class="saas-card" style="margin-bottom: var(--saas-spacing-md); padding: var(--saas-spacing-md); background: var(--saas-card-bg); border-color: var(--saas-border);">"""
    if title:
        resolved = _resolve_icon(icon) if icon else ""
        icon_html = f'<span style="margin-right: var(--saas-spacing-sm); font-size: 1.1rem;">{resolved}</span>' if resolved else ""
        subtitle_html = f'<div style="font-size: 0.75rem; color: var(--saas-text-muted); margin-top: 2px;">{subtitle}</div>' if subtitle else ""
        html += f"""
        <div style="margin-bottom: var(--saas-spacing-sm); border-bottom: 1px solid var(--saas-border); padding-bottom: 4px;">
            <div style="font-family: 'Outfit', sans-serif; font-size: 0.95rem; font-weight: 600; color: var(--saas-text-main); display: flex; align-items: center;">
                {icon_html}{title}
            </div>
            {subtitle_html}
        </div>
        """
    safe_html(html)

def saas_card_end():
    """End a SaaS-styled card container."""
    safe_html("</div>")

def saas_metric(label, value, delta=None, delta_color="normal", icon=None, help=None):
    """
    Render a modern SaaS metric card.
    delta_color: "normal" (green up, red down), "inverse" (red up, green down)
    help: Tooltip text appearing on title hover.
    """
    delta_html = ""
    if delta:
        color = "var(--saas-success)" if (delta.startswith("+") and delta_color=="normal") or (delta.startswith("-") and delta_color=="inverse") else "var(--saas-danger)"
        delta_html = f'<div style="font-size: 0.7rem; font-weight: 600; color: {color}; margin-top: 2px;">{delta}</div>'

    icon_html = f"""
    <div style="width: 24px; height: 24px; border-radius: 6px; background: var(--saas-primary-light); opacity: 0.15; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; margin-bottom: 4px;">
        {icon}
    </div>
    """ if icon else ""

    # Reliable CSS Tooltip
    help_html = f'''
    <div class="saas-tooltip">
        ⓘ
        <span class="saas-tooltip-text">{help}</span>
    </div>
    ''' if help else ""

    safe_html(f"""
    <div class="saas-card" style="height: 100%; padding: var(--saas-spacing-sm); background: var(--saas-card-bg); border-color: var(--saas-border);">
        {icon_html}
        <div style="font-size: 0.7rem; color: var(--saas-text-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; display: flex; align-items: center;">
            {label} {help_html}
        </div>
        <div style="font-family: 'Outfit', sans-serif; font-size: 1.25rem; font-weight: 700; color: var(--saas-text-main); margin-top: 2px;">{value}</div>
        {delta_html}
    </div>
    """)

def saas_badge(text, style="info"):
    """Render a modern theme-aware badge (pill). style: success, warning, danger, info, neutral"""
    styles = {
        "success": ("var(--saas-success)", "var(--saas-success-bg)"),
        "warning": ("var(--saas-warning)", "var(--saas-warning-bg)"),
        "danger": ("var(--saas-danger)", "var(--saas-danger-bg)"),
        "info": ("var(--saas-info)", "var(--saas-info-bg)"),
        "neutral": ("var(--saas-text-muted)", "var(--saas-hover-bg)")
    }
    fg, bg = styles.get(style, styles["info"])
    
    return f"""
    <span style="background-color: {bg}; color: {fg}; padding: 0.15rem 0.6rem; border-radius: 9999px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; white-space: nowrap; border: 1px solid {bg};">
        {text}
    </span>
    """

def saas_alert(message, style="info", title=None):
    """Render a clean SaaS alert banner."""
    styles = {
        "success": ("var(--saas-success)", "var(--saas-success-bg)", "✓"),
        "warning": ("var(--saas-warning)", "var(--saas-warning-bg)", "⚠️"),
        "danger": ("var(--saas-danger)", "var(--saas-danger-bg)", "✕"),
        "info": ("var(--saas-info)", "var(--saas-info-bg)", "ℹ️")
    }
    color, bg, icon = styles.get(style, styles["info"])
    
    title_html = f'<div style="font-weight: 700; margin-bottom: 2px; font-size: 0.85rem;">{title}</div>' if title else ""
    
    safe_html(f"""
    <div style="background-color: {bg}; border-left: 3px solid {color}; padding: var(--saas-spacing-sm); border-radius: var(--saas-radius-sm); margin-bottom: var(--saas-spacing-md); display: flex; align-items: flex-start;">
        <div style="margin-right: var(--saas-spacing-sm); font-size: 0.9rem; line-height: 1.2;">{icon}</div>
        <div style="color: var(--saas-text-main); font-size: 0.8rem;">{title_html}{message}</div>
    </div>
    """)

def saas_section_header(title, subtitle=None, icon=None):
    """Render a clean section header with optional icon."""
    resolved = _resolve_icon(icon) if icon else ""
    icon_html = f'<span style="margin-right: var(--saas-spacing-sm);">{resolved}</span>' if resolved else ""
    subtitle_html = f'<div style="color: var(--saas-text-muted); font-size: 0.8rem; margin-top: 2px;">{subtitle}</div>' if subtitle else ""
    safe_html(f"""
    <div style="margin: var(--saas-spacing-lg) 0 var(--saas-spacing-sm) 0; border-bottom: 2px solid var(--saas-primary); padding-bottom: 2px; display: inline-block; min-width: 120px;">
        <h2 style="font-family: 'Outfit', sans-serif; font-weight: 700; color: var(--saas-text-main); font-size: 1.15rem; margin: 0; display: flex; align-items: center;">
            {icon_html}{title}
        </h2>
        {subtitle_html}
    </div>
    <div style="margin-bottom: var(--saas-spacing-sm);"></div>
    """)

def saas_markdown(content: str):
    """
    Render markdown with enhanced SaaS typography and spacing optimized for readability.
    提升 SaaS 報告閱讀體驗的 Markdown 渲染。
    """
    safe_html(f"""
    <div class="saas-markdown-container">
        {st.markdown(content, unsafe_allow_html=False)}
    </div>
    <style>
        .saas-markdown-container div[data-testid="stMarkdownContainer"] p {{
            font-size: 1.05rem !important;
            line-height: 1.7 !important;
            color: var(--saas-text-main) !important;
            margin-bottom: 1.2rem !important;
        }}
        .saas-markdown-container div[data-testid="stMarkdownContainer"] h1,
        .saas-markdown-container div[data-testid="stMarkdownContainer"] h2,
        .saas-markdown-container div[data-testid="stMarkdownContainer"] h3 {{
            margin-top: 2rem !important;
            margin-bottom: 1rem !important;
            font-family: 'Outfit', sans-serif !important;
        }}
        .saas-markdown-container div[data-testid="stMarkdownContainer"] li {{
            font-size: 1.05rem !important;
            line-height: 1.6 !important;
            margin-bottom: 0.5rem !important;
        }}
        .saas-markdown-container div[data-testid="stMarkdownContainer"] code {{
            background-color: var(--saas-hover-bg) !important;
            padding: 0.2rem 0.4rem !important;
            border-radius: 4px !important;
            font-size: 0.9em !important;
        }}
    </style>
    """)

def saas_report_block(title, content, icon=None, block_type="neutral"):
    """
    Render a structured report block (Smart Block) for key insights or metrics.
    渲染一個結構化的報告區塊（智慧區塊），用於呈現核心洞察或指標。
    """
    styles = {
        "success": ("var(--saas-success)", "var(--saas-success-bg)"),
        "warning": ("var(--saas-warning)", "var(--saas-warning-bg)"),
        "danger": ("var(--saas-danger)", "var(--saas-danger-bg)"),
        "info": ("var(--saas-info)", "var(--saas-info-bg)"),
        "neutral": ("var(--saas-primary)", "var(--saas-card-bg)")
    }
    color, bg = styles.get(block_type, styles["neutral"])
    resolved_icon = _resolve_icon(icon) if icon else ""
    
    safe_html(f"""
    <div style="background: {bg}; border-left: 4px solid {color}; padding: 1.25rem; border-radius: 8px; margin: 1.5rem 0; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
        <div style="display: flex; align-items: center; margin-bottom: 0.75rem;">
            <span style="margin-right: 0.75rem; color: {color}; font-size: 1.25rem;">{resolved_icon}</span>
            <span style="font-family: 'Outfit', sans-serif; font-weight: 700; color: var(--saas-text-main); font-size: 1rem;">{title}</span>
        </div>
        <div style="font-size: 1rem; line-height: 1.6; color: var(--saas-text-main);">
            {content}
        </div>
    </div>
    """)
