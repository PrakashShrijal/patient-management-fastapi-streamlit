"""
Patient Management System — Streamlit Dashboard
================================================
Dual-mode: connects to FastAPI backend if reachable, otherwise falls back to
direct JSON file I/O with the same Pydantic validation & BMI logic from main.py.
"""

import json
import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pydantic import BaseModel, Field, computed_field, ValidationError
from typing import Annotated, Literal, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models (mirrored from main.py)
# ─────────────────────────────────────────────────────────────────────────────

class Patient(BaseModel):
    id: Annotated[str, Field(..., description="ID of the patient", examples=["P001"])]
    name: Annotated[str, Field(..., description="Name of the patient")]
    city: Annotated[str, Field(..., description="City where the patient is living")]
    age: Annotated[int, Field(..., gt=0, lt=120, description="Age of the patient")]
    gender: Annotated[Literal["male", "female", "others"], Field(..., description="Gender of the patient")]
    height: Annotated[float, Field(..., gt=0, description="Height of the patient in mtrs")]
    weight: Annotated[float, Field(..., gt=0, description="Weight of the patient in kgs")]

    @computed_field
    @property
    def bmi(self) -> float:
        return round(self.weight / (self.height ** 2), 2)

    @computed_field
    @property
    def verdict(self) -> str:
        if self.bmi < 18.5:
            return "Underweight"
        elif self.bmi < 25:
            return "Normal"
        elif self.bmi < 30:
            return "Overweight"
        else:
            return "Obese"


class PatientUpdate(BaseModel):
    name: Annotated[Optional[str], Field(default=None)]
    city: Annotated[Optional[str], Field(default=None)]
    age: Annotated[Optional[int], Field(default=None, gt=0)]
    gender: Annotated[Optional[Literal["male", "female", "others"]], Field(default=None)]
    height: Annotated[Optional[float], Field(default=None, gt=0)]
    weight: Annotated[Optional[float], Field(default=None, gt=0)]


# ─────────────────────────────────────────────────────────────────────────────
# Data-layer helpers — Standalone (direct JSON) mode
# ─────────────────────────────────────────────────────────────────────────────

DATA_FILE = os.path.join(os.path.dirname(__file__), "patients.json")


def _load_json() -> dict:
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def _standalone_view() -> dict:
    return _load_json()


def _standalone_get(patient_id: str):
    data = _load_json()
    if patient_id not in data:
        return None, "Patient not found"
    return data[patient_id], None


def _standalone_create(patient: Patient):
    data = _load_json()
    if patient.id in data:
        return False, "Patient already exists"
    data[patient.id] = patient.model_dump(exclude={"id"})
    _save_json(data)
    return True, "Patient created successfully"


def _standalone_update(patient_id: str, updates: dict):
    data = _load_json()
    if patient_id not in data:
        return False, "Patient not found"
    existing = data[patient_id]
    existing.update(updates)
    existing["id"] = patient_id
    try:
        p = Patient(**existing)
        data[patient_id] = p.model_dump(exclude={"id"})
        _save_json(data)
        return True, "Patient updated successfully"
    except ValidationError as e:
        return False, str(e)


def _standalone_delete(patient_id: str):
    data = _load_json()
    if patient_id not in data:
        return False, "Patient not found"
    del data[patient_id]
    _save_json(data)
    return True, "Patient deleted successfully"


def _standalone_sort(sort_by: str, order: str) -> list:
    data = _load_json()
    reverse = order == "desc"
    return sorted(data.values(), key=lambda x: x.get(sort_by, 0), reverse=reverse)


# ─────────────────────────────────────────────────────────────────────────────
# API-mode helpers
# ─────────────────────────────────────────────────────────────────────────────

def _api_reachable(base_url: str) -> bool:
    try:
        r = requests.get(base_url.rstrip("/") + "/", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _api_view(base_url: str) -> dict:
    r = requests.get(base_url.rstrip("/") + "/view", timeout=5)
    r.raise_for_status()
    return r.json()


def _api_get(base_url: str, patient_id: str):
    r = requests.get(f"{base_url.rstrip('/')}/patient/{patient_id}", timeout=5)
    if r.status_code == 404:
        return None, "Patient not found"
    r.raise_for_status()
    return r.json(), None


def _api_create(base_url: str, payload: dict):
    r = requests.post(base_url.rstrip("/") + "/create", json=payload, timeout=5)
    if r.status_code == 400:
        return False, r.json().get("detail", "Bad request")
    r.raise_for_status()
    return True, r.json().get("message", "Created")


def _api_update(base_url: str, patient_id: str, updates: dict):
    r = requests.put(f"{base_url.rstrip('/')}/edit/{patient_id}", json=updates, timeout=5)
    if r.status_code in (400, 404):
        return False, r.json().get("detail", "Error")
    r.raise_for_status()
    return True, r.json().get("message", "Updated")


def _api_delete(base_url: str, patient_id: str):
    r = requests.delete(f"{base_url.rstrip('/')}/delete/{patient_id}", timeout=5)
    if r.status_code == 404:
        return False, "Patient not found"
    r.raise_for_status()
    return True, r.json().get("message", "Deleted")


def _api_sort(base_url: str, sort_by: str, order: str) -> list:
    r = requests.get(
        base_url.rstrip("/") + "/sort",
        params={"sort_by": sort_by, "order": order},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Unified data layer — picks API or standalone automatically
# ─────────────────────────────────────────────────────────────────────────────

def get_data_mode() -> tuple[bool, str]:
    """Returns (use_api: bool, base_url: str)."""
    base_url = st.session_state.get("api_url", "http://127.0.0.1:8000")
    use_api = st.session_state.get("api_reachable", False)
    return use_api, base_url


def fetch_all() -> dict:
    use_api, base_url = get_data_mode()
    if use_api:
        try:
            return _api_view(base_url)
        except Exception:
            pass
    return _standalone_view()


def fetch_patient(pid: str):
    use_api, base_url = get_data_mode()
    if use_api:
        try:
            return _api_get(base_url, pid)
        except Exception as e:
            return None, str(e)
    return _standalone_get(pid)


def create_patient_data(payload: dict):
    use_api, base_url = get_data_mode()
    if use_api:
        try:
            return _api_create(base_url, payload)
        except Exception as e:
            return False, str(e)
    # Validate with Pydantic locally
    try:
        p = Patient(**payload)
        return _standalone_create(p)
    except ValidationError as e:
        return False, str(e)


def update_patient_data(patient_id: str, updates: dict):
    use_api, base_url = get_data_mode()
    if use_api:
        try:
            return _api_update(base_url, patient_id, updates)
        except Exception as e:
            return False, str(e)
    return _standalone_update(patient_id, updates)


def delete_patient_data(patient_id: str):
    use_api, base_url = get_data_mode()
    if use_api:
        try:
            return _api_delete(base_url, patient_id)
        except Exception as e:
            return False, str(e)
    return _standalone_delete(patient_id)


def sort_patients_data(sort_by: str, order: str) -> list:
    use_api, base_url = get_data_mode()
    if use_api:
        try:
            return _api_sort(base_url, sort_by, order)
        except Exception:
            pass
    return _standalone_sort(sort_by, order)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

VERDICT_COLORS = {
    "Underweight": "#3b82f6",
    "Normal":      "#22c55e",
    "Overweight":  "#f59e0b",
    "Obese":       "#ef4444",
}

VERDICT_EMOJI = {
    "Underweight": "🔵",
    "Normal":      "🟢",
    "Overweight":  "🟡",
    "Obese":       "🔴",
}


def records_to_df(data: dict) -> pd.DataFrame:
    if not data:
        return pd.DataFrame()
    rows = []
    for pid, info in data.items():
        row = {"id": pid, **info}
        rows.append(row)
    df = pd.DataFrame(rows)
    # Ensure numeric columns
    for col in ["age", "height", "weight", "bmi"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def bmi_badge(verdict: str) -> str:
    color = VERDICT_COLORS.get(verdict, "#6b7280")
    emoji = VERDICT_EMOJI.get(verdict, "⚪")
    return f"{emoji} {verdict}"


# ─────────────────────────────────────────────────────────────────────────────
# Page configs & styles
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Patient Management System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Sidebar nav buttons */
    div[data-testid="stSidebarContent"] .stButton > button {
        width: 100%;
        text-align: left;
        border: none;
        background: transparent;
        font-size: 0.95rem;
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        color: inherit;
        transition: background 0.15s;
    }
    div[data-testid="stSidebarContent"] .stButton > button:hover {
        background: rgba(255,255,255,0.08);
    }
    /* KPI cards */
    .kpi-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .kpi-label { font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px; }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #f1f5f9; }
    .kpi-sub   { font-size: 0.75rem; color: #64748b; margin-top: 2px; }
    /* Mode badge */
    .mode-badge {
        display: inline-block;
        font-size: 0.72rem;
        padding: 2px 8px;
        border-radius: 20px;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — navigation & connection settings
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏥 Patient Manager")
    st.divider()

    # API URL config
    try:
        default_url = st.secrets.get("API_URL", "http://127.0.0.1:8000")
    except Exception:
        default_url = "http://127.0.0.1:8000"
    api_url_input = st.text_input("FastAPI URL", value=default_url, key="api_url_input")

    if st.button("🔌 Connect / Refresh"):
        st.session_state["api_url"] = api_url_input
        reachable = _api_reachable(api_url_input)
        st.session_state["api_reachable"] = reachable
        if reachable:
            st.success("Connected to FastAPI ✓")
        else:
            st.warning("API unreachable — using local JSON")

    # Init session state defaults
    if "api_url" not in st.session_state:
        st.session_state["api_url"] = api_url_input
    if "api_reachable" not in st.session_state:
        st.session_state["api_reachable"] = _api_reachable(api_url_input)

    mode_label = "🟢 API Mode" if st.session_state.get("api_reachable") else "🟡 Standalone Mode"
    st.caption(mode_label)

    st.divider()
    st.markdown("**Navigation**")

    pages = {
        "🏠 Overview & Analytics": "overview",
        "📋 View & Sort Patients": "view",
        "➕ Add New Patient":      "add",
        "✏️  Update & Delete":     "edit",
    }

    if "page" not in st.session_state:
        st.session_state["page"] = "overview"

    for label, key in pages.items():
        if st.button(label, key=f"nav_{key}"):
            st.session_state["page"] = key

    st.divider()
    st.caption("Patient Management System v1.0")


current_page = st.session_state.get("page", "overview")


# ─────────────────────────────────────────────────────────────────────────────
# Page 1 — Overview & Analytics
# ─────────────────────────────────────────────────────────────────────────────

if current_page == "overview":
    st.title("🏠 Overview & Analytics")

    data = fetch_all()
    df = records_to_df(data)

    if df.empty:
        st.info("No patient records found. Add patients using the **Add New Patient** page.")
        st.stop()

    # ── KPI row ──────────────────────────────────────────────────────────────
    total = len(df)
    avg_bmi = df["bmi"].mean() if "bmi" in df.columns else 0
    avg_age = df["age"].mean() if "age" in df.columns else 0
    gender_counts = df["gender"].value_counts().to_dict() if "gender" in df.columns else {}

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">TOTAL PATIENTS</div>'
            f'<div class="kpi-value">{total}</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">AVERAGE BMI</div>'
            f'<div class="kpi-value">{avg_bmi:.1f}</div>'
            f'<div class="kpi-sub">kg/m²</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">AVERAGE AGE</div>'
            f'<div class="kpi-value">{avg_age:.1f}</div>'
            f'<div class="kpi-sub">years</div></div>',
            unsafe_allow_html=True,
        )
    with col4:
        gender_str = "  ·  ".join(f"{g}: {c}" for g, c in gender_counts.items())
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">GENDER SPLIT</div>'
            f'<div class="kpi-value" style="font-size:1.1rem;padding-top:0.4rem">{gender_str}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts ───────────────────────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("BMI Category Breakdown")
        if "verdict" in df.columns:
            verdict_counts = df["verdict"].value_counts().reset_index()
            verdict_counts.columns = ["Category", "Count"]
            color_map = {k: v for k, v in VERDICT_COLORS.items()}
            fig_pie = px.pie(
                verdict_counts,
                names="Category",
                values="Count",
                color="Category",
                color_discrete_map=color_map,
                hole=0.45,
            )
            fig_pie.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#f1f5f9",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with chart_col2:
        st.subheader("Gender Distribution")
        if "gender" in df.columns:
            gender_df = df["gender"].value_counts().reset_index()
            gender_df.columns = ["Gender", "Count"]
            fig_bar = px.bar(
                gender_df,
                x="Gender",
                y="Count",
                color="Gender",
                color_discrete_sequence=["#6366f1", "#ec4899", "#14b8a6"],
                text="Count",
            )
            fig_bar.update_layout(
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#f1f5f9",
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            )
            fig_bar.update_traces(textposition="outside")
            st.plotly_chart(fig_bar, use_container_width=True)

    # ── BMI Scatter ───────────────────────────────────────────────────────────
    st.subheader("Age vs BMI (by Category)")
    if {"age", "bmi", "verdict", "name"}.issubset(df.columns):
        fig_scatter = px.scatter(
            df,
            x="age",
            y="bmi",
            color="verdict",
            hover_name="name",
            hover_data={"id": True, "gender": True, "city": True},
            color_discrete_map=VERDICT_COLORS,
            size="bmi",
            size_max=25,
        )
        # BMI reference lines
        for threshold, label in [(18.5, "Underweight"), (25, "Normal"), (30, "Overweight")]:
            fig_scatter.add_hline(
                y=threshold,
                line_dash="dot",
                line_color="rgba(255,255,255,0.3)",
                annotation_text=f"  {label} /{threshold}",
                annotation_font_color="#94a3b8",
            )
        fig_scatter.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#f1f5f9",
            xaxis=dict(title="Age (years)", showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(title="BMI (kg/m²)", showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            legend_title_text="BMI Category",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    # ── Weight Distribution Histogram ─────────────────────────────────────────
    st.subheader("Weight Distribution")
    if "weight" in df.columns:
        fig_hist = px.histogram(
            df,
            x="weight",
            color="verdict",
            color_discrete_map=VERDICT_COLORS,
            nbins=15,
            labels={"weight": "Weight (kg)"},
        )
        fig_hist.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#f1f5f9",
            bargap=0.05,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig_hist, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page 2 — View & Sort Patients
# ─────────────────────────────────────────────────────────────────────────────

elif current_page == "view":
    st.title("📋 View & Sort Patients")

    # ── Sort controls ─────────────────────────────────────────────────────────
    with st.expander("⚙️ Sort Options", expanded=False):
        sort_col1, sort_col2, sort_col3 = st.columns([2, 2, 1])
        with sort_col1:
            sort_field = st.selectbox("Sort by", ["height", "weight", "bmi"], key="sort_field")
        with sort_col2:
            sort_order = st.selectbox("Order", ["asc", "desc"], key="sort_order")
        with sort_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            apply_sort = st.button("Apply Sort")

    if apply_sort or st.session_state.get("sorted_data") is not None:
        if apply_sort:
            sorted_records = sort_patients_data(sort_field, sort_order)
            st.session_state["sorted_data"] = sorted_records
            st.session_state["sorted_by"] = (sort_field, sort_order)
        else:
            sorted_records = st.session_state.get("sorted_data", [])
        if sorted_records:
            sb, so = st.session_state.get("sorted_by", (sort_field, sort_order))
            st.caption(f"Sorted by **{sb}** ({so})")
            sort_df = pd.DataFrame(sorted_records)
            st.dataframe(sort_df, use_container_width=True, hide_index=True)
        else:
            st.info("No records found.")
    else:
        # Default view — all patients
        data = fetch_all()
        df = records_to_df(data)

        if df.empty:
            st.info("No patient records found.")
        else:
            # Search / filter
            search_col1, search_col2, search_col3 = st.columns([3, 2, 2])
            with search_col1:
                search_query = st.text_input("🔍 Search by name or city", key="search_q")
            with search_col2:
                filter_gender = st.multiselect(
                    "Gender", options=df["gender"].unique().tolist() if "gender" in df.columns else [],
                    key="filter_gender",
                )
            with search_col3:
                filter_verdict = st.multiselect(
                    "BMI Category",
                    options=df["verdict"].unique().tolist() if "verdict" in df.columns else [],
                    key="filter_verdict",
                )

            filtered = df.copy()
            if search_query:
                mask = (
                    filtered["name"].str.contains(search_query, case=False, na=False)
                    | filtered["city"].str.contains(search_query, case=False, na=False)
                )
                filtered = filtered[mask]
            if filter_gender:
                filtered = filtered[filtered["gender"].isin(filter_gender)]
            if filter_verdict:
                filtered = filtered[filtered["verdict"].isin(filter_verdict)]

            st.markdown(f"**{len(filtered)}** patient(s) found")
            st.dataframe(filtered, use_container_width=True, hide_index=True)

    st.divider()

    # ── Single patient lookup ─────────────────────────────────────────────────
    st.subheader("🔎 Quick Patient Lookup")
    lookup_col1, lookup_col2 = st.columns([3, 1])
    with lookup_col1:
        lookup_id = st.text_input("Enter Patient ID (e.g. P001)", key="lookup_id")
    with lookup_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        do_lookup = st.button("Fetch Patient")

    if do_lookup and lookup_id:
        record, err = fetch_patient(lookup_id.strip())
        if err:
            st.error(f"❌ {err}")
        else:
            st.success("Patient found!")
            detail_cols = st.columns(4)
            fields = [
                ("Name", record.get("name", "—")),
                ("City", record.get("city", "—")),
                ("Age", record.get("age", "—")),
                ("Gender", record.get("gender", "—")),
            ]
            for col, (label, val) in zip(detail_cols, fields):
                col.metric(label, val)
            detail_cols2 = st.columns(4)
            fields2 = [
                ("Height (m)", record.get("height", "—")),
                ("Weight (kg)", record.get("weight", "—")),
                ("BMI", record.get("bmi", "—")),
                ("Verdict", bmi_badge(record.get("verdict", "—"))),
            ]
            for col, (label, val) in zip(detail_cols2, fields2):
                col.metric(label, val)


# ─────────────────────────────────────────────────────────────────────────────
# Page 3 — Add New Patient
# ─────────────────────────────────────────────────────────────────────────────

elif current_page == "add":
    st.title("➕ Add New Patient")

    with st.form("add_patient_form", clear_on_submit=False):
        st.subheader("Patient Details")
        col1, col2 = st.columns(2)

        with col1:
            pid   = st.text_input("Patient ID *", placeholder="e.g. P007")
            name  = st.text_input("Full Name *", placeholder="e.g. John Doe")
            city  = st.text_input("City *", placeholder="e.g. Delhi")
            age   = st.number_input("Age *", min_value=1, max_value=119, value=25, step=1)

        with col2:
            gender = st.selectbox("Gender *", ["male", "female", "others"])
            height = st.number_input("Height (metres) *", min_value=0.1, max_value=3.0, value=1.70, step=0.01, format="%.2f")
            weight = st.number_input("Weight (kg) *", min_value=0.1, max_value=500.0, value=70.0, step=0.1, format="%.1f")

        # Live BMI preview inside the form
        live_bmi = round(weight / (height ** 2), 2) if height > 0 else 0
        if live_bmi < 18.5:
            live_verdict = "Underweight"
        elif live_bmi < 25:
            live_verdict = "Normal"
        elif live_bmi < 30:
            live_verdict = "Overweight"
        else:
            live_verdict = "Obese"

        bmi_color = VERDICT_COLORS.get(live_verdict, "#6b7280")
        st.markdown(
            f"**Live BMI Preview:** `{live_bmi}` — "
            f'<span style="color:{bmi_color};font-weight:600">{VERDICT_EMOJI.get(live_verdict,"")} {live_verdict}</span>',
            unsafe_allow_html=True,
        )

        submitted = st.form_submit_button("✅ Create Patient", type="primary", use_container_width=True)

    if submitted:
        if not pid.strip():
            st.error("❌ Patient ID is required.")
        elif not name.strip():
            st.error("❌ Patient name is required.")
        elif not city.strip():
            st.error("❌ City is required.")
        else:
            payload = {
                "id":     pid.strip().upper(),
                "name":   name.strip(),
                "city":   city.strip(),
                "age":    int(age),
                "gender": gender,
                "height": float(height),
                "weight": float(weight),
            }
            ok, msg = create_patient_data(payload)
            if ok:
                st.success(f"🎉 {msg}")
                st.balloons()
                st.markdown(
                    f"**BMI:** `{live_bmi}` — "
                    f'<span style="color:{bmi_color};font-weight:600">{live_verdict}</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.error(f"❌ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Page 4 — Update & Delete Patient
# ─────────────────────────────────────────────────────────────────────────────

elif current_page == "edit":
    st.title("✏️ Update & Delete Patient")

    data = fetch_all()

    if not data:
        st.info("No patient records found. Add patients first.")
        st.stop()

    patient_ids = sorted(data.keys())
    selected_id = st.selectbox("Select Patient ID", options=patient_ids, key="edit_select_id")

    if selected_id:
        record = data.get(selected_id, {})

        st.subheader(f"Editing: {record.get('name', selected_id)}  ({selected_id})")

        # ── Edit form ─────────────────────────────────────────────────────────
        with st.form("edit_patient_form"):
            col1, col2 = st.columns(2)

            with col1:
                e_name   = st.text_input("Full Name", value=record.get("name", ""))
                e_city   = st.text_input("City", value=record.get("city", ""))
                e_age    = st.number_input("Age", min_value=1, max_value=119, value=int(record.get("age", 25)), step=1)

            with col2:
                gender_opts = ["male", "female", "others"]
                curr_gender = record.get("gender", "male")
                g_index = gender_opts.index(curr_gender) if curr_gender in gender_opts else 0
                e_gender = st.selectbox("Gender", options=gender_opts, index=g_index)
                e_height = st.number_input("Height (metres)", min_value=0.1, max_value=3.0,
                                           value=float(record.get("height", 1.70)), step=0.01, format="%.2f")
                e_weight = st.number_input("Weight (kg)", min_value=0.1, max_value=500.0,
                                           value=float(record.get("weight", 70.0)), step=0.1, format="%.1f")

            # Live BMI preview
            e_bmi = round(e_weight / (e_height ** 2), 2) if e_height > 0 else 0
            if e_bmi < 18.5:
                e_verdict = "Underweight"
            elif e_bmi < 25:
                e_verdict = "Normal"
            elif e_bmi < 30:
                e_verdict = "Overweight"
            else:
                e_verdict = "Obese"

            bmi_col = VERDICT_COLORS.get(e_verdict, "#6b7280")
            st.markdown(
                f"**Updated BMI Preview:** `{e_bmi}` — "
                f'<span style="color:{bmi_col};font-weight:600">{VERDICT_EMOJI.get(e_verdict,"")} {e_verdict}</span>',
                unsafe_allow_html=True,
            )

            update_btn = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)

        if update_btn:
            updates = {
                "name":   e_name.strip() or None,
                "city":   e_city.strip() or None,
                "age":    int(e_age),
                "gender": e_gender,
                "height": float(e_height),
                "weight": float(e_weight),
            }
            # Remove None values so only changed fields are sent
            updates = {k: v for k, v in updates.items() if v is not None}
            ok, msg = update_patient_data(selected_id, updates)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")

        st.divider()

        # ── Delete section ────────────────────────────────────────────────────
        st.subheader("⚠️ Delete Patient")
        st.warning(
            f"This will permanently remove **{record.get('name', selected_id)}** (ID: `{selected_id}`) from the system."
        )

        # Two-step confirmation
        if "confirm_delete_id" not in st.session_state:
            st.session_state["confirm_delete_id"] = None

        if st.session_state["confirm_delete_id"] != selected_id:
            if st.button("🗑️ Delete This Patient", type="secondary"):
                st.session_state["confirm_delete_id"] = selected_id
                st.rerun()
        else:
            st.error("⚠️ Are you sure? This action cannot be undone.")
            conf_col1, conf_col2 = st.columns(2)
            with conf_col1:
                if st.button("✅ Yes, delete permanently", type="primary"):
                    ok, msg = delete_patient_data(selected_id)
                    if ok:
                        st.success(f"🗑️ {msg}")
                        st.session_state["confirm_delete_id"] = None
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
            with conf_col2:
                if st.button("❌ Cancel"):
                    st.session_state["confirm_delete_id"] = None
                    st.rerun()
