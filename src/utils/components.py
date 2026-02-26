"""
   2026 SaaS Component Library for Streamlit
   Reusable UI elements for a professional Investment Advisor experience.
"""
import streamlit as st
from src.utils.ui import safe_html

def saas_card_start(title=None, subtitle=None, icon=None):
    """Start a SaaS-styled card container."""
    html = f"""<div class="saas-card" style="margin-bottom: var(--saas-spacing-md); padding: var(--saas-spacing-md); background: var(--saas-card-bg); border-color: var(--saas-border);">"""
    if title:
        icon_html = f'<span style="margin-right: var(--saas-spacing-sm); font-size: 1.1rem;">{icon}</span>' if icon else ""
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

    # Tooltip CSS/HTML
    help_html = f'''<span style="cursor: help; margin-left: 4px;" title="{help}">ⓘ</span>''' if help else ""

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
    icon_html = f'<span style="margin-right: var(--saas-spacing-sm);">{icon}</span>' if icon else ""
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
