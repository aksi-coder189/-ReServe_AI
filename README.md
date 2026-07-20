# ReServe AI

**An AI-agent-powered surplus food & donation dispatch platform.**

ReServe AI connects donors, NGOs, and volunteers through an automated
matching pipeline: a surplus alert comes in (as free text — e.g. a WhatsApp
message), an NLP agent parses it, a matching agent finds the best-fit NGO by
capacity and proximity, and a dispatch agent assigns the nearest available
volunteer — all backed by a real FastAPI + SQLite backend and a trained
`RandomForestRegressor` demand-forecasting model.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Portals & Roles](#portals--roles)
- [API Reference](#api-reference)
- [Data Model](#data-model)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Overview

The platform is built around a five-agent pipeline:

| Agent | What it does |
|---|---|
| **NLP Agent** | Extracts food type, quantity, and spoilage window from a raw text message |
| **Food Safety Agent** | Heuristic freshness scan from an optional photo upload |
| **Matching Agent** | Finds the best NGO by capacity fit + haversine distance |
| **Dispatch Agent** | Assigns the nearest available volunteer with sufficient vehicle capacity |
| **Forecast Agent** | Trained `RandomForestRegressor` predicting neighborhood surplus hotspots by hour/weekend/rain |

Every stage is real and server-side (in `agents.py` / `ml_model.py`) — the
frontend (`project.html`) is a single-file SPA that renders the live results
of each pipeline run, with no hardcoded data.

## Architecture

```
┌─────────────────┐        REST (JSON)        ┌──────────────────────┐
│   project.html   │  ────────────────────────▶ │   FastAPI (main.py)  │
│  (single-file    │ ◀──────────────────────── │                       │
│   SPA, no build   │                            │  agents.py  (NLP /   │
│   step needed)    │                            │   matching / dispatch)│
└─────────────────┘                            │  ml_model.py (forecast)│
                                                 │  models.py  (SQLAlchemy)│
                                                 └──────────┬────────────┘
                                                             │
                                                    ┌────────▼────────┐
                                                    │ reserve_ai.db    │
                                                    │ (SQLite)         │
                                                    └──────────────────┘
```

The frontend polls/refreshes from the backend after every action
(`refreshFromBackend()`) — there is no client-side mock data left; NGOs,
volunteers, dispatches, analytics, and notifications are all live queries.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy + SQLite |
| ML | scikit-learn (`RandomForestRegressor`), joblib |
| Frontend | Vanilla JS SPA (no framework/build step), Tailwind CSS (CDN), Chart.js, Leaflet |
| Auth | Email/password (see [Known Limitations](#known-limitations)) |

## Project Structure

```
ReServe_ai 
├── main.py            # FastAPI app — all routes
├── models.py           # SQLAlchemy ORM models
├── schemas.py           # Pydantic request/response schemas
├── agents.py             # NLP / Matching / Dispatch agent logic
├── ml_model.py             # Trains & serves the forecast RandomForestRegressor
├── database.py               # SQLite engine/session setup
├── migrate_db.py               # One-time migration for pre-existing databases
├── requirements.txt              # Python dependencies
├── project.html                   # The entire frontend (open directly in a browser)
├── reserve_ai.db                    # SQLite database (created automatically)
└── forecast_model.joblib              # Trained forecast model (created automatically)
```

## Getting Started

### Prerequisites

- Python 3.10+
- A modern browser (Chrome/Edge/Firefox)

### 1. Install dependencies

```bash
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

### 2. (Existing databases only) Run the migration

If you already have a `reserve_ai.db` from an earlier version of this
project, run the migration once — SQLAlchemy's `create_all()` only creates
*new* tables, it never alters existing ones:

```bash
python migrate_db.py
```

Safe to re-run; it skips any column that already exists. Fresh setups (no
`reserve_ai.db` yet) can skip this step entirely.

### 3. Start the server

```bash
uvicorn main:app --reload --port 8000
```

The forecast model trains itself automatically on first request if
`forecast_model.joblib` doesn't exist yet. Interactive API docs are at
`http://127.0.0.1:8000/docs`.

### 4. Open the frontend

Open `project.html` directly in a browser (double-click it, or
`open project.html` / `start project.html`). No build step, no dev server —
it's a static file that talks to the API at `http://127.0.0.1:8000`.

> If your backend runs somewhere other than `127.0.0.1:8000`, update the
> `API_BASE` constant near the top of the `<script>` block in `project.html`.

## Portals & Roles

The platform has four entry points from the landing page, each backed by a
signup/login flow:

| Portal | Who it's for | What they can do |
|---|---|---|
| **Matching Agent Hub** | Ops staff | Ingest surplus alerts, watch the live 5-agent pipeline run, review the dispatch ledger and geospatial map |
| **NGO Instance** | NGO staff | Monitor incoming shipments and capacity against their own node |
| **Donor Portal** | Donors | Donate money to an NGO of choice (mock payment flow), or donate surplus food/goods (runs the same real matching pipeline) |
| **Volunteer Portal** | Volunteers | See jobs assigned to them by the Dispatch Agent and mark pickup/in-transit/delivered — status updates write straight to SQLite |

Signing up as a **Volunteer** or **NGO** automatically provisions a linked
operational record (`Volunteer`/`NGO` row), so that account can actually be
matched by the pipeline — not just log in and see nothing. New volunteer
accounts are also seeded with one demo job so the portal is never empty on
first login.

The **Matching Agent Hub** and **Volunteer Portal** are cross-linked: orders
created from the Matching Agent Hub or Donor Portal are immediately visible
in the Volunteer Portal (filtered to "your jobs" when logged in as a specific
volunteer, or shown fleet-wide otherwise).

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/ngos` | List all NGOs |
| `GET` | `/volunteers` | List all volunteers |
| `POST` | `/pipeline/run` | Run the full NLP → Matching → Dispatch pipeline on a raw message |
| `GET` | `/dispatch` | Full dispatch ledger |
| `POST` | `/dispatch/{alert_id}/advance?status=...` | Advance a dispatch's status (pickup → in transit → delivered) |
| `POST` | `/predict/forecast` | Trained-model hotspot forecast per neighborhood |
| `GET` | `/history/{alert_id}` | Timeline events for one dispatch |
| `GET` | `/notifications` | Recent notification feed |
| `GET` | `/analytics/summary` | Rollup stats (meals saved, CO₂ estimate, success rate, etc.) |
| `POST` | `/donate/money` | Record a money donation to an NGO (mock payment) |
| `GET` | `/donate/money?donor_email=&ngo_code=` | List money donations, optionally filtered |
| `POST` | `/signup` | Create an account (`agent` \| `ngo` \| `donor` \| `volunteer`) |
| `POST` | `/login` | Authenticate; returns the account's linked `vol_id`/`ngo_id` if applicable |

Full interactive documentation (with request/response schemas) is available
at `/docs` while the server is running.

## Data Model

Core tables (see `models.py` for full column definitions):

- **`Donor`** / **`NGO`** / **`Volunteer`** — network participants; NGO and
  Volunteer rows can be linked to a `User` account via `owner_email`
- **`Food`** — a surplus entry parsed from an alert message
- **`Dispatch`** (`dispatch_ledger` table) — the core record linking a
  `Food` entry to an `NGO` and a `Volunteer`, with status/ETA/confidence
- **`HistoryEvent`** — append-only timeline log per `alert_id`
- **`Notification`** — feed of system events (dispatch created, money donated, etc.)
- **`MoneyDonation`** — cash donations from a donor to an NGO
- **`Prediction`** — logged forecast queries
- **`User`** — signup/login credentials and role

## Known Limitations

- **Payment flow is a mock.** The Donor Portal's money-donation form
  (UPI/Card/Net Banking) is a UI simulation for demo purposes — no real
  payment gateway (Razorpay, Stripe, etc.) is integrated, and no money
  actually moves. Wire in a real gateway's server-side confirmation before
  using this in production.
- **Passwords are stored in plaintext** in the `users` table. Fine for a
  demo/hackathon build; not acceptable for production — hash with
  `bcrypt`/`argon2` before deploying anywhere real.
- **CORS is wide open** (`allow_origins=["*"]"`) for local development
  convenience. Restrict this to your actual frontend origin before deploying.
- **No route/session guarding.** Any dashboard URL can be opened without
  being logged in (some fall back to a read-only/fleet-wide view instead of
  gating access).

## Roadmap

- Real payment gateway integration for the Donor Portal
- Password hashing + session tokens (JWT) instead of plaintext + client-held state
- Google Maps integration for live donor → NGO → volunteer routing
- Role-based route guarding
- Swap `ml_model.py`'s synthetic training data for real logged surplus history
