# 🌦️ Multi-Agent GenAI Weather Assistant

> **An intelligent, physics-aware weather analysis system** built with **Gemini LLMs**, **Google Vertex AI**, and the **Agent Development Kit (ADK)** — designed to transform natural-language weather questions into deterministic, data-grounded insights.

---

## 🧠 Overview

The **Multi-Agent GenAI Weather Assistant** enables users to ask queries such as  
> “Compare rainfall trends between New York and Buffalo last month,”  
and automatically obtain precise, unit-aware, and explainable weather summaries.

It dynamically interprets **locations**, **time windows**, and **variables**, chooses the appropriate **Open-Meteo API** (forecast, recent, or archive), and when relevant, adds **physics-based explanations** retrieved via **Vertex AI RAG**.

---

## 🧩 System Architecture
'''
user query → weather_coordinator (Gemini-2.5-pro)
├── weather_query_agent
│   ├── geocode_place() → lat/lon, timezone
│   ├── pick_variables() → temperature_2m, precipitation, etc.
│   ├── detect_model_hint() → GFS / ECMWF / ERA5 / ICON
│   ├── fetch_openmeteo() → dynamic endpoint selection
│   └── summarise_weather() → concise, unit-aware answer
└── physics_rag_agent (optional)
    └── Vertex AI RAG Retrieval → physics mechanism note
'''


Each agent runs under **Google ADK**, exposing standardized `AgentTool` / `FunctionTool` interfaces for deterministic chaining and reproducible outputs.

---

## ⚙️ Core Components

### 1. `weather_coordinator`
- Parses flexible queries about **place + time + variable**.  
- Builds an internal planning JSON (`start_date`, `end_date`, `granularity`, `mode`, `timezone`).  
- Delegates sub-tasks to specialized agents.  
- Merges weather data with physics explanations.

### 2. `weather_query_agent`
- Converts ambiguous natural language into deterministic Open-Meteo calls.  
- Detects implicit variables (e.g., “windy” → `wind_speed_10m`).  
- Infers **hindcast / forecast / mixed** modes from phrasing.  
- Ensures strict hourly/daily variable mapping and timezone awareness.  
- Returns clear, unit-labeled results.

### 3. `physics_rag_agent`
- Triggered when users ask *“why”* or request mechanisms.  
- Retrieves concise, mechanism-level explanations from a **Vertex AI RAG corpus**.  
- Produces ≤ 4-sentence, citation-backed physics notes (e.g., adiabatic warming, Coriolis effects).

### 4. Toolchain Highlights

| Tool | Function |
|------|-----------|
| `geocode_place` | Maps city/state/country/IATA codes → lat/lon + IANA timezone |
| `pick_variables` | Infers canonical variables (`temperature_2m`, `precipitation_sum`, etc.) |
| `detect_model_hint` | Extracts model references (GFS, ECMWF, ERA5) |
| `fetch_openmeteo` | Dynamically selects API endpoint (forecast / recent / archive) |
| `summarise_weather` | Computes min/max/mean and generates final answer |
| `compare_weather` | Fetches and compares variables across two locations |

---

## 🧮 Example Query → Response Flow

**Query:**  
> “Why was San Francisco colder than San Diego yesterday?”

**Flow:**
1. `parse_comparative_query()` extracts two cities.  
2. `geocode_place()` resolves lat/lon + timezones.  
3. `pick_variables()` infers `temperature_2m`.  
4. `fetch_openmeteo()` retrieves hourly forecast data.  
5. `compare_weather()` computes mean/min/max ΔT.  
6. `physics_rag_agent` adds a retrieved note:  
   *“Marine-layer cooling from coastal upwelling keeps San Francisco cooler than San Diego.”*

**Example Output:**
San Francisco (37.77 N, –122.42 E) vs San Diego (32.72 N, –117.16 E)
2024-07-03 UTC (local: America/Los Angeles)
temperature_2m mean difference ≈ 6 °C lower in San Francisco due to marine-layer influence.
Citations: Marine Layer Dynamics — Section Coastal Inversions


---

## ☁️ Technologies & Ecosystem

| Category | Stack |
|-----------|-------|
| **LLM Core** | Google Gemini 2.5 Pro / Gemini 2.0 Flash |
| **Framework** | Google Agent Development Kit (ADK Python SDK) |
| **APIs & Data** | Open-Meteo (Forecast / Archive Endpoints) |
| **Retrieval** | Vertex AI RAG with custom physics corpus |
| **Cloud Platform** | Google Vertex AI + Compute Engine |
| **Languages & Libs** | Python 3.12, requests, dotenv, timezonefinder |
| **Design Patterns** | Multi-Agent Orchestration · RAG Pipelines · Dynamic Routing |
| **Version Control** | GitHub Actions + Poetry Environment Mgmt |

---

## 🧱 Key Engineering Highlights

- **Multi-Agent Orchestration:** LLM-driven agents for retrieval, reasoning, and summarization.  
- **Dynamic API Switching:** Auto-routes between forecast/recent/archive based on context.  
- **Deterministic Weather Parsing:** Enforces ISO-date plans and granularity integrity.  
- **Physics-Aware RAG Integration:** Retrieves verifiable scientific mechanisms.  
- **Cloud-Native Deployment:** End-to-end on Google Vertex AI with secure credentials.  
- **Robust Error Handling:** Fallbacks for geocoding, time modes, and Open-Meteo errors.

---

## 📊 Demonstrated Skills & Expertise

This project demonstrates **Yavar Khan’s** ability to build:
- **LLM-driven multi-agent architectures** combining reasoning and retrieval.  
- **API-integrated AI systems** with dynamic data pipelines and error-resilient tooling.  
- **Cloud-deployed GenAI applications** on Vertex AI and ADK.  
- **Physics-informed AI interfaces** bridging ML, data science, and software engineering.  
- Expertise in **prompt design, tool chaining, and system governance.**

---

## 🚀 Setup & Execution

```bash
# Clone the repository
git clone https://github.com/VectorWorkX/wx-event-reliability.git
cd wx-event-reliability

# Sync dependencies
uv sync    # or poetry install

# Run locally
poetry run adk web
# → launches FastAPI endpoint for the Weather Coordinator
