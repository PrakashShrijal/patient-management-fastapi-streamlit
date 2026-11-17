# 🏥 Patient Management System

A full-stack patient management application built with **FastAPI** (backend REST API) and **Streamlit** (interactive dashboard).

---

## 📂 Project Structure

```
patient-management-fastapi-main/
├── main.py          # FastAPI backend (REST API)
├── app.py           # Streamlit dashboard (frontend)
├── patients.json    # JSON data store
├── requirements.txt # Python dependencies
└── README.md
```

---

## 🚀 Running Locally

### Option A — Streamlit Dashboard only (Standalone Mode)

The dashboard reads/writes `patients.json` directly using the same Pydantic validation and BMI logic from `main.py`. No separate server needed.

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the dashboard
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

### Option B — Full Stack (FastAPI + Streamlit)

Run both processes in separate terminals:

**Terminal 1 — FastAPI backend:**
```bash
uvicorn main:app --reload
# API available at http://127.0.0.1:8000
# Interactive docs at http://127.0.0.1:8000/docs
```

**Terminal 2 — Streamlit dashboard:**
```bash
streamlit run app.py
```

In the Streamlit sidebar, enter `http://127.0.0.1:8000` in the **FastAPI URL** field and click **Connect / Refresh**. The dashboard will switch to API mode and proxy all reads/writes through the FastAPI server.


---

## 🌐 API Endpoints (FastAPI)

| Method | Endpoint              | Description                        |
|--------|-----------------------|------------------------------------|
| GET    | `/`                   | Health check                       |
| GET    | `/view`               | List all patients                  |
| GET    | `/patient/{id}`       | Get a single patient by ID         |
| GET    | `/sort`               | Sort patients by height/weight/bmi |
| POST   | `/create`             | Create a new patient               |
| PUT    | `/edit/{id}`          | Update an existing patient         |
| DELETE | `/delete/{id}`        | Delete a patient                   |

Interactive Swagger docs: **http://127.0.0.1:8000/docs**

---

## 📊 Dashboard Features

| Page | Features |
|------|----------|
| 🏠 Overview & Analytics | KPI cards (total, avg BMI, avg age, gender split), Plotly charts: BMI category pie, gender bar, age-vs-BMI scatter, weight histogram |
| 📋 View & Sort Patients | Searchable/filterable dataframe, sort by height/weight/bmi, single-patient quick lookup |
| ➕ Add New Patient       | Validated form, live BMI preview, success/error feedback |
| ✏️ Update & Delete       | Pre-filled edit form, two-step delete confirmation |

---

## 🧮 BMI Calculation

```
BMI = weight (kg) / height² (m²)
```

| BMI Range  | Category     |
|------------|--------------|
| < 18.5     | Underweight  |
| 18.5–24.9  | Normal       |
| 25.0–29.9  | Overweight   |
| ≥ 30.0     | Obese        |

---

## 🛠️ Tech Stack

- **FastAPI** + **Pydantic v2** — backend REST API with computed BMI fields
- **Streamlit** — interactive web dashboard
- **Plotly** — interactive charts
- **Pandas** — dataframe manipulation
- **Uvicorn** — ASGI server for FastAPI
