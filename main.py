from datetime import datetime
from typing import List, Optional
import uuid

from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from database import Base, engine, get_db
from agents import parse_whatsapp_surplus, run_matching_agent, run_dispatch_agent
from ml_model import predict_hotspot, NEIGHBORHOODS

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ReServe AI API",
    version="1.0.0"
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your frontend's origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Seed data — mirrors the frontend's NETWORK_NGOS / FLEET_VOLUNTEERS constants,
# but now lives in SQLite instead of a hardcoded JS array.
# ---------------------------------------------------------------------------
@app.on_event("startup")
def seed_if_empty():
    from database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(models.NGO).count() == 0:
            db.add_all([
                models.NGO(ngo_id="NGO_001", name="Hope Foundation", capacity_servings=20,
                           accepts_cooked=True, lat=28.7050, lon=77.1000),
                models.NGO(ngo_id="NGO_002", name="Delhi Hunger Relief", capacity_servings=200,
                           accepts_cooked=True, lat=28.7100, lon=77.1150),
            ])
        if db.query(models.Volunteer).count() == 0:
            db.add_all([
                models.Volunteer(vol_id="VOL_089", name="Aman", vehicle="bike", capacity=30,
                                  speed_kmph=22, lat=28.7042, lon=77.1026, status="idle"),
                models.Volunteer(vol_id="VOL_102", name="Priya", vehicle="car", capacity=150,
                                  speed_kmph=38, lat=28.7060, lon=77.1040, status="idle"),
            ])
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Network registry
# ---------------------------------------------------------------------------
@app.get("/ngos", response_model=List[schemas.NGOOut])
def list_ngos(db: Session = Depends(get_db)):
    return db.query(models.NGO).all()


@app.get("/volunteers", response_model=List[schemas.VolunteerOut])
def list_volunteers(db: Session = Depends(get_db)):
    return db.query(models.Volunteer).all()


# ---------------------------------------------------------------------------
# The multi-agent dispatch pipeline (NLP → Matching → Dispatch), backed by SQLite
# ---------------------------------------------------------------------------
@app.post("/pipeline/run")
def run_pipeline(payload: schemas.SurplusAlertIn, db: Session = Depends(get_db)):
    surplus = parse_whatsapp_surplus(payload.message, payload.lat, payload.lon,
                                      payload.spoil_hours_override)

    food = models.Food(food_type=surplus["food_type"], quantity_servings=surplus["quantity_servings"],
                        time_to_spoil_hours=surplus["time_to_spoil_hours"],
                        freshness_score=payload.freshness_score,
                        lat=surplus["location_lat"], lon=surplus["location_lon"])
    db.add(food)
    db.commit()
    db.refresh(food)

    ngos = [{"ngo_id": n.ngo_id, "name": n.name, "capacity_servings": n.capacity_servings,
             "accepts_cooked": n.accepts_cooked, "lat": n.lat, "lon": n.lon}
            for n in db.query(models.NGO).all()]
    match = run_matching_agent(surplus, ngos)

    if not match["match_found"]:
        return {"surplus": surplus, "match": match, "dispatch": None}

    volunteers = [{"vol_id": v.vol_id, "name": v.name, "vehicle": v.vehicle, "capacity": v.capacity,
                    "speed_kmph": v.speed_kmph, "lat": v.lat, "lon": v.lon}
                   for v in db.query(models.Volunteer).all()]
    dispatch_res = run_dispatch_agent(surplus, match["dispatch_urgency"], volunteers)

    ngo_row = db.query(models.NGO).filter_by(ngo_id=match["best_ngo_id"]).first()
    vol_row = db.query(models.Volunteer).filter_by(vol_id=dispatch_res["assigned_volunteer_id"]).first()

    alert_id = f"AL-{900 + db.query(models.Dispatch).count() + 1}"
    dispatch = models.Dispatch(
        alert_id=alert_id, food_id=food.id, ngo_id=ngo_row.id if ngo_row else None,
        volunteer_id=vol_row.id if vol_row else None, cargo=surplus["food_type"],
        volume=surplus["quantity_servings"], urgency=match["dispatch_urgency"],
        status=f"En-route Via Volunteer {dispatch_res['assigned_volunteer_id']}",
        eta_mins=dispatch_res["estimated_pickup_mins"], confidence_score=match["confidence_score"],
    )
    db.add(dispatch)
    db.add(models.HistoryEvent(alert_id=alert_id, label="Donor Alert Received"))
    db.add(models.HistoryEvent(alert_id=alert_id, label="Matched & Volunteer Assigned"))
    db.add(models.Notification(alert_id=alert_id, message=f"Dispatch {alert_id} created → {match['best_ngo_name']}", tone="emerald"))
    db.commit()

    return {
        "status": "success",
        "alert_id": alert_id,
        "surplus": surplus,
        "match": match,

        "food_alert": {
            "id": food.id,
            "food_type": food.food_type,
            "quantity_servings": food.quantity_servings
        },

        "matched_ngo": {
            "id": ngo_row.ngo_id if ngo_row else None,
            "name": ngo_row.name if ngo_row else None
        },
        "assigned_volunteer": {
            "id": vol_row.vol_id if vol_row else None,
            "name": vol_row.name if vol_row else None
        },

        "dispatch": dispatch_res,

        "dispatch_record": {
            "alert_id": dispatch.alert_id,
            "status": dispatch.status,
            "eta": dispatch.eta_mins,
            "created_at": dispatch.created_at
        },

        "locations": {
            "donor": {
                "lat": food.lat,
                "lon": food.lon
            },

            "ngo": {
                "lat": ngo_row.lat,
                "lon": ngo_row.lon
            },

            "volunteer": {
                "lat": vol_row.lat,
                "lon": vol_row.lon
            }
        },

        "agent_logs": [
            f"Surplus Detection Agent detected {food.food_type}",
            f"Matching Agent selected {ngo_row.name}",
            f"Dispatch Agent assigned {vol_row.name}",
            f"Estimated pickup {dispatch.eta_mins} minutes"
        ]
    }

@app.get("/dispatch", response_model=List[schemas.DispatchOut])
def list_dispatches(db: Session = Depends(get_db)):
    return db.query(models.Dispatch)\
        .order_by(models.Dispatch.created_at.desc())\
        .all()

@app.post("/dispatch/{alert_id}/advance")
def advance_dispatch_status(alert_id: str, status: str, db: Session = Depends(get_db)):
    """Called by the QR-scan endpoint on the NGO side, or a delivery-lifecycle simulator."""
    d = db.query(models.Dispatch).filter_by(alert_id=alert_id).first()
    if not d:
        raise HTTPException(404, "Alert not found")
    d.status = status
    if status == "Delivered / Reconciled":
        d.delivered_at = datetime.utcnow()
    db.add(models.HistoryEvent(alert_id=alert_id, label=status))
    db.commit()
    return {"alert_id": alert_id, "status": status}


# ---------------------------------------------------------------------------
# Forecast (real trained RandomForestRegressor — see ml_model.py)
# ---------------------------------------------------------------------------
@app.post("/predict/forecast")
def forecast(query: schemas.ForecastQuery):
    return [predict_hotspot(n, query.hour, query.is_weekend, query.is_raining) for n in NEIGHBORHOODS]


# ---------------------------------------------------------------------------
# History + notifications + analytics rollups
# ---------------------------------------------------------------------------
@app.get("/history/{alert_id}")
def get_history(alert_id: str, db: Session = Depends(get_db)):
    events = db.query(models.HistoryEvent).filter_by(alert_id=alert_id).order_by(models.HistoryEvent.timestamp).all()
    return [{"label": e.label, "timestamp": e.timestamp.isoformat()} for e in events]


@app.get("/notifications", response_model=List[schemas.NotificationOut])
def get_notifications(db: Session = Depends(get_db)):
    return db.query(models.Notification).order_by(models.Notification.created_at.desc()).limit(50).all()


@app.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db)):
    dispatches = db.query(models.Dispatch).all()
    total_servings = sum(d.volume for d in dispatches)
    delivered = sum(1 for d in dispatches if d.status == "Delivered / Reconciled")
    success_pct = round((delivered / len(dispatches)) * 100) if dispatches else 100
    avg_eta = round(sum(d.eta_mins for d in dispatches) / len(dispatches)) if dispatches else 0
    active_dispatches = sum(
        1 for d in dispatches
        if d.status != "Delivered / Reconciled"
    )
    return {
        "total_food_saved_servings": total_servings,
        "co2_saved_kg_estimate": round(total_servings * 0.3),
        "meals_served": total_servings,
        "success_rate_percent": success_pct,
        "average_eta_mins": avg_eta,
        "total_dispatches": len(dispatches),
        "total_ngos": db.query(models.NGO).count(),

        "total_volunteers": db.query(models.Volunteer).count(),

        "active_dispatches": active_dispatches
    }

@app.post("/donate/money", response_model=schemas.MoneyDonationOut)
def donate_money(payload: schemas.MoneyDonationIn, db: Session = Depends(get_db)):
    """Records a money donation to an NGO. NOTE: this is a MOCK payment flow for
    demo purposes — no real payment gateway (Razorpay/Stripe/etc.) is wired up,
    no money actually moves. Swap in a real gateway's server-side confirmation
    here before using this in production."""
    ngo = db.query(models.NGO).filter_by(ngo_id=payload.ngo_code).first()
    if not ngo:
        raise HTTPException(404, "NGO not found")

    donor_name = payload.donor_name or "Anonymous Donor"
    donation = models.MoneyDonation(
        donor_email=payload.donor_email, donor_name=donor_name,
        ngo_code=ngo.ngo_id, ngo_name=ngo.name, amount=payload.amount,
        payment_method=payload.payment_method,
        transaction_id=f"TXN-{uuid.uuid4().hex[:10].upper()}", status="success",
    )
    db.add(donation)
    db.add(models.Notification(
        alert_id=None,
        message=f"💰 ₹{payload.amount:.0f} donated to {ngo.name} by {donor_name}",
        tone="emerald",
    ))
    db.commit()
    db.refresh(donation)
    return donation


@app.get("/donate/money", response_model=List[schemas.MoneyDonationOut])
def list_money_donations(donor_email: Optional[str] = None, ngo_code: Optional[str] = None,
                          db: Session = Depends(get_db)):
    q = db.query(models.MoneyDonation)
    if donor_email:
        q = q.filter(models.MoneyDonation.donor_email == donor_email)
    if ngo_code:
        q = q.filter(models.MoneyDonation.ngo_code == ngo_code)
    return q.order_by(models.MoneyDonation.created_at.desc()).all()


def _seed_demo_job_if_none(db: Session, volunteer: models.Volunteer):
    """Guarantees a volunteer always has at least one job to see and act on in
    the Volunteer Portal, instead of a permanently empty dashboard the first
    time they log in — a real order from the Matching Agent will show up
    alongside/replace this the moment one gets assigned to them."""
    has_job = db.query(models.Dispatch).filter_by(volunteer_id=volunteer.id).first()
    if has_job:
        return
    ngo = db.query(models.NGO).first()
    if not ngo:
        return
    food = models.Food(food_type="Assorted Surplus Meals", quantity_servings=25,
                        time_to_spoil_hours=3, lat=volunteer.lat, lon=volunteer.lon)
    db.add(food)
    db.commit()
    db.refresh(food)
    alert_id = f"AL-{900 + db.query(models.Dispatch).count() + 1}"
    dispatch = models.Dispatch(
        alert_id=alert_id, food_id=food.id, ngo_id=ngo.id, volunteer_id=volunteer.id,
        cargo=food.food_type, volume=food.quantity_servings, urgency="Medium",
        status=f"En-route Via Volunteer {volunteer.vol_id}", eta_mins=15, confidence_score=0.8,
    )
    db.add(dispatch)
    db.add(models.HistoryEvent(alert_id=alert_id, label="Donor Alert Received"))
    db.add(models.HistoryEvent(alert_id=alert_id, label="Matched & Volunteer Assigned"))
    db.add(models.Notification(alert_id=alert_id, message=f"Dispatch {alert_id} created → {ngo.name}", tone="emerald"))
    db.commit()


@app.post("/signup")
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):

    existing = db.query(models.User).filter(
        models.User.email == user.email
    ).first()

    if existing:
        raise HTTPException(400, "Email already exists")

    new_user = models.User(
        entity_name=user.entity_name,
        email=user.email,
        password=user.password,
        role=user.role
    )

    db.add(new_user)
    db.commit()

    # Auto-provision the operational record this role needs to actually take part
    # in the dispatch pipeline — a volunteer needs a Volunteer row to be matchable
    # by the Dispatch Agent, an NGO needs an NGO row to be matchable by the
    # Matching Agent, and a donor needs a Donor row to have donation history.
    display_name = user.entity_name or user.email.split("@")[0]
    if user.role == "volunteer":
        vol_count = db.query(models.Volunteer).count()
        new_vol = models.Volunteer(
            vol_id=f"VOL_{200 + vol_count}", name=display_name, vehicle="bike",
            capacity=30, speed_kmph=22, lat=28.7041, lon=77.1025, status="idle",
            owner_email=user.email,
        )
        db.add(new_vol)
        db.commit()
        db.refresh(new_vol)
        _seed_demo_job_if_none(db, new_vol)
    elif user.role == "ngo":
        ngo_count = db.query(models.NGO).count()
        db.add(models.NGO(
            ngo_id=f"NGO_{100 + ngo_count}", name=display_name, capacity_servings=50,
            accepts_cooked=True, lat=28.7050, lon=77.1000, owner_email=user.email,
        ))
    elif user.role == "donor":
        db.add(models.Donor(name=display_name, email=user.email))
    db.commit()

    return {"message": "Signup Successful"}

@app.post("/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):

    existing = db.query(models.User).filter(
        models.User.email == user.email,
        models.User.password == user.password
    ).first()

    if not existing:
        raise HTTPException(401, "Invalid Credentials")

    # Hand back this account's operational identity so the frontend knows
    # "which volunteer / which NGO / which donor" it's actually logged in as.
    # Self-healing: if this is an older account created before auto-provisioning
    # existed (or before a DB migration was run), provision it now instead of
    # leaving the user permanently stuck with no volunteer/NGO profile.
    identity = {}
    display_name = existing.entity_name or existing.email.split("@")[0]
    if existing.role == "volunteer":
        v = db.query(models.Volunteer).filter_by(owner_email=existing.email).first()
        if not v:
            vol_count = db.query(models.Volunteer).count()
            v = models.Volunteer(
                vol_id=f"VOL_{200 + vol_count}", name=display_name, vehicle="bike",
                capacity=30, speed_kmph=22, lat=28.7041, lon=77.1025, status="idle",
                owner_email=existing.email,
            )
            db.add(v)
            db.commit()
            db.refresh(v)
        _seed_demo_job_if_none(db, v)
        identity["vol_id"] = v.vol_id
    elif existing.role == "ngo":
        n = db.query(models.NGO).filter_by(owner_email=existing.email).first()
        if not n:
            ngo_count = db.query(models.NGO).count()
            n = models.NGO(
                ngo_id=f"NGO_{100 + ngo_count}", name=display_name, capacity_servings=50,
                accepts_cooked=True, lat=28.7050, lon=77.1000, owner_email=existing.email,
            )
            db.add(n)
            db.commit()
            db.refresh(n)
        identity["ngo_id"] = n.ngo_id

    return {
        "message": "Login Successful",
        "role": existing.role,
        "entity_name": existing.entity_name,
        **identity,
    }

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        "project.html",
        {"request": request}
    )
