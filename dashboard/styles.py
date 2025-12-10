from pathlib import Path


def load_base_css() -> str:
    css_path = Path(__file__).resolve().parent / "style.css"
    return css_path.read_text(encoding="utf-8")


def build_custom_css(css_text: str) -> str:
    return f"""
    <style>
    {css_text}

    /* Global Streamlit overrides */
    .main {{
        background: var(--bg);
        padding: 0 !important;
    }}

    .block-container {{
        padding: 2rem 1rem !important;
        max-width: 800px !important;
    }}

    /* Typography */
    h1, h2, h3, h4, h5, h6 {{
        font-family: "Inter", "Segoe UI", Roboto, Arial, sans-serif !important;
        color: var(--text) !important;
    }}

    h1 {{
        font-size: 2rem !important;
        font-weight: 800 !important;
        text-align: center;
        margin-bottom: 2rem !important;
        color: var(--accent) !important;
    }}

    h2 {{
        font-size: 1.25rem !important;
        font-weight: 700 !important;
        margin-top: 1.5rem !important;
    }}

    /* Buttons */
    .stButton > button {{
        background: var(--accent) !important;
        color: #fff !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 8px 16px !important;
        font-weight: 700 !important;
        font-family: "Inter", sans-serif !important;
        transition: all 0.2s !important;
        box-shadow: 0 2px 8px rgba(30, 75, 138, 0.2) !important;
        width: 100%;
    }}

    .stButton > button:hover {{
        background: var(--accent-light) !important;
        box-shadow: 0 4px 12px rgba(95, 168, 224, 0.3) !important;
        transform: translateY(-1px);
    }}

    .stButton > button:active {{
        transform: translateY(0);
    }}

    /* Number Input */
    .stNumberInput input {{
        background: #fff !important;
        border: 1px solid #cdd6e3 !important;
        border-radius: 6px !important;
        padding: 8px !important;
        font-family: "Inter", sans-serif !important;
        transition: border-color 0.2s !important;
    }}

    .stNumberInput input:focus {{
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px rgba(30, 75, 138, 0.1) !important;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        margin-top: 30px;
        gap: 10px;
        justify-content: center;
        background: transparent;
        border-bottom: none !important;
    }}

    .stTabs [data-baseweb="tab"] {{
        background: var(--btn) !important;
        border: 1px solid rgba(0, 0, 0, 0.1) !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
        font-weight: 600 !important;
        color: var(--text) !important;
        transition: all 0.2s !important;
    }}

    .stTabs [data-baseweb="tab"]:hover {{
        background: var(--accent-light) !important;
        color: #fff !important;
    }}

    .stTabs [aria-selected="true"] {{
        background: var(--accent) !important;
        color: #fff !important;
        box-shadow: 0 4px 10px rgba(30, 75, 138, 0.2) !important;
    }}

    /* Checkbox */
    .stCheckbox {{
        font-family: "Inter", sans-serif !important;
    }}

    /* Cards */
    .metric-card {{
        background: white;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(0, 0, 0, 0.05);
        text-align: center;
        transition: all 0.2s;
    }}

    .metric-card:hover {{
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
        transform: translateY(-2px);
    }}

    .metric-title {{
        font-size: 0.875rem;
        color: var(--text-soft);
        font-weight: 600;
        margin-bottom: 0.5rem;
    }}

    .metric-value {{
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--accent);
    }}

    /* Status badge */
    .status-badge {{
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
    }}

    .status-good {{
        background: #e6f7e6;
        color: #2b612b;
    }}

    .status-bad {{
        background: #fdeaea;
        color: #8c2e2e;
    }}

    /* Countdown Display */
    .countdown-display {{
        background: var(--display);
        border-radius: 14px;
        padding: 2rem;
        text-align: center;
        border: 1px solid rgba(0, 0, 0, 0.08);
        box-shadow: inset 0 1px 1px rgba(255,255,255,0.5);
        margin: 1.5rem 0;
    }}

    .phase-label {{
        font-weight: 700;
        color: var(--text-soft);
        font-size: 0.875rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
    }}

    .phase-time {{
        font-size: 3.5rem;
        font-weight: 800;
        color: var(--accent);
        margin: 0.75rem 0;
        font-family: 'Courier New', monospace;
    }}

    .sub-time {{
        font-size: 0.875rem;
        color: var(--text-soft);
        margin-top: 0.5rem;
    }}

    /* Plan Summary */
    .plan-summary-grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.75rem;
        margin: 1rem 0;
        background: white;
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }}

    .plan-item {{
        text-align: center;
        padding: 0.5rem;
    }}

    .plan-label {{
        font-size: 0.75rem;
        color: var(--text-soft);
        margin-bottom: 0.25rem;
    }}

    .plan-value {{
        font-size: 1.125rem;
        font-weight: 700;
        color: var(--accent);
    }}

    /* Water Items */
    .water-milestone {{
        background: white;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #dde3ef;
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: all 0.2s;
    }}

    .water-milestone:hover {{
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border-color: var(--accent-light);
    }}

    .water-milestone.active {{
        background: #e3f2fd;
        border-color: var(--accent-light);
    }}

    /* Info boxes */
    .info-box {{
        background: white;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid var(--accent);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }}

    /* Hide default Streamlit elements */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}

    /* Spacing improvements */
    .element-container {{
        margin: 0.5rem 0;
    }}

    div[data-testid="stVerticalBlock"] > div {{
        gap: 0.5rem;
    }}
    </style>
    """
