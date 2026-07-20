"""
SQLAlchemy models for ReServe AI.

Replaces the frontend's hardcoded arrays (NETWORK_NGOS, FLEET_VOLUNTEERS,
dispatchLedger) with real persisted tables in SQLite.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Donor(Base):
    __tablename__ = "donors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True, index=True)  # links back to users.email for a signed-up donor account
    phone = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    food_entries = relationship("Food", back_populates="donor")


class NGO(Base):
    __tablename__ = "ngos"
    id = Column(Integer, primary_key=True, index=True)
    ngo_id = Column(String, unique=True, index=True)   # e.g. NGO_001
    name = Column(String, nullable=False)
    capacity_servings = Column(Integer, default=0)
    accepts_cooked = Column(Boolean, default=True)
    lat = Column(Float)
    lon = Column(Float)
    owner_email = Column(String, nullable=True, index=True)  # links back to users.email for a signed-up NGO account

    dispatches = relationship("Dispatch", back_populates="ngo")


class Volunteer(Base):
    __tablename__ = "volunteers"
    id = Column(Integer, primary_key=True, index=True)
    vol_id = Column(String, unique=True, index=True)   # e.g. VOL_089
    name = Column(String, nullable=False)
    vehicle = Column(String, default="bike")
    capacity = Column(Integer, default=30)
    speed_kmph = Column(Float, default=20)
    lat = Column(Float)
    lon = Column(Float)
    status = Column(String, default="idle")  # idle | en_route | delivering
    owner_email = Column(String, nullable=True, index=True)  # links back to users.email for a signed-up volunteer account

    dispatches = relationship("Dispatch", back_populates="volunteer")


class Food(Base):
    __tablename__ = "food_entries"
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=True)
    food_type = Column(String)
    quantity_servings = Column(Integer)
    time_to_spoil_hours = Column(Float, default=4)
    freshness_score = Column(Float, nullable=True)   # from the Food Safety Vision Agent
    lat = Column(Float)
    lon = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    donor = relationship("Donor", back_populates="food_entries")


class Dispatch(Base):
    __tablename__ = "dispatch_ledger"
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, unique=True, index=True)  # e.g. AL-903
    food_id = Column(Integer, ForeignKey("food_entries.id"), nullable=True)
    ngo_id = Column(Integer, ForeignKey("ngos.id"), nullable=True)
    volunteer_id = Column(Integer, ForeignKey("volunteers.id"), nullable=True)
    cargo = Column(String)
    volume = Column(Integer)
    urgency = Column(String)          # High | Medium | Low
    status = Column(String, default="En-route")
    eta_mins = Column(Integer)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    ngo = relationship("NGO", back_populates="dispatches")
    volunteer = relationship("Volunteer", back_populates="dispatches")

    @property
    def ngo_code(self):
        """String NGO code (e.g. NGO_001) — what the frontend actually needs, not the internal int FK."""
        return self.ngo.ngo_id if self.ngo else None

    @property
    def volunteer_code(self):
        """String volunteer code (e.g. VOL_089) — what the frontend actually needs, not the internal int FK."""
        return self.volunteer.vol_id if self.volunteer else None


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, index=True)
    neighborhood = Column(String)
    hour = Column(Integer)
    is_weekend = Column(Boolean)
    is_raining = Column(Boolean)
    predicted_servings = Column(Float)
    hotspot_severity_percent = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class HistoryEvent(Base):
    """Append-only event log — powers the frontend timeline + analytics charts."""
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, index=True)
    label = Column(String)          # e.g. "Donor Alert Received", "Delivered"
    timestamp = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String, index=True, nullable=True)
    message = Column(String)
    tone = Column(String, default="emerald")   # emerald | amber | sky | red
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MoneyDonation(Base):
    """A donor's cash donation to an NGO — the 'donate money' half of the Donor Portal.
    (The 'donate material/goods' half reuses the existing Food → Dispatch pipeline.)"""
    __tablename__ = "money_donations"
    id = Column(Integer, primary_key=True, index=True)
    donor_email = Column(String, nullable=True, index=True)
    donor_name = Column(String, nullable=True)
    ngo_code = Column(String, index=True)
    ngo_name = Column(String)
    amount = Column(Float)
    payment_method = Column(String)  # upi | card | netbanking
    transaction_id = Column(String, unique=True, index=True)
    status = Column(String, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    entity_name = Column(String, nullable=True)

    email = Column(String, unique=True, nullable=False)

    password = Column(String, nullable=False)

    role = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)