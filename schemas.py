from datetime import datetime

from pydantic import BaseModel
from typing import Optional, List

class NGOOut(BaseModel):
    ngo_id: str
    name: str
    capacity_servings: int
    accepts_cooked: bool
    lat: float
    lon: float

    class Config:
        from_attributes = True

class VolunteerOut(BaseModel):
    vol_id: str
    name: str
    vehicle: str
    capacity: int
    speed_kmph: float
    lat: float
    lon: float
    status: str

    class Config:
        from_attributes = True

class DispatchOut(BaseModel):
    alert_id: str
    cargo: str
    volume: int
    urgency: str
    status: str
    eta_mins: int
    confidence_score: float
    created_at: datetime
    ngo_code: Optional[str] = None
    volunteer_code: Optional[str] = None

    class Config:
        from_attributes = True

class AnalyticsSummaryResponse(BaseModel):
    total_food_saved_servings: int
    total_dispatches: int
    fulfillment_rate: float

    class Config:
        from_attributes = True

class NotificationOut(BaseModel):
    id: int
    alert_id: Optional[str] = None
    message: str
    tone: str
    created_at: datetime

    class Config:
        from_attributes = True

class SurplusAlertIn(BaseModel):
    message: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    freshness_score: Optional[float] = None
    spoil_hours_override: Optional[float] = None

class ForecastQuery(BaseModel):
    hour: int
    is_weekend: bool
    is_raining: bool

class MoneyDonationIn(BaseModel):
    ngo_code: str
    amount: float
    payment_method: str  # upi | card | netbanking
    donor_name: Optional[str] = None
    donor_email: Optional[str] = None

class MoneyDonationOut(BaseModel):
    transaction_id: str
    ngo_code: str
    ngo_name: str
    amount: float
    payment_method: str
    status: str
    donor_name: Optional[str] = None
    donor_email: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    entity_name: Optional[str] = None
    email: str
    password: str
    role: str


class UserLogin(BaseModel):
    email: str
    password: str