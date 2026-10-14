"""Seed script - runs at container start after `alembic upgrade head`.

Adds sample VEHICLES (editable in the UI) and default fuel prices, only when the
tables are empty. It deliberately does NOT add any facilities: fuel stations,
chargers, restaurants etc. come only from real providers (OpenStreetMap /
Open Charge Map) and are cached in the database as routes are planned.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import settings  # noqa: E402
from app.database.session import SessionLocal  # noqa: E402
from app.models.models import FuelPrice, Vehicle  # noqa: E402

# Typical manufacturer / real-world figures; users can edit them in the Vehicles page.
VEHICLES = [
    {"name": "Maruti WagonR CNG (Bi-fuel)", "vehicle_type": "car", "fuel_type": "bifuel",
     "secondary_fuel_type": "petrol", "tank_capacity": 32.0, "efficiency": 18.0, "current_fuel_pct": 80.0,
     "cng_tank_capacity": 8.0, "cng_efficiency": 26.0, "current_cng_pct": 100.0},
    {"name": "Hyundai Creta (Petrol)", "vehicle_type": "car", "fuel_type": "petrol",
     "tank_capacity": 50.0, "efficiency": 14.0, "current_fuel_pct": 100.0},
    {"name": "Tata Nexon EV", "vehicle_type": "car", "fuel_type": "electric",
     "tank_capacity": 40.5, "efficiency": 6.5, "current_fuel_pct": 100.0,
     "battery_capacity_kwh": 40.5, "ev_efficiency": 6.5, "current_battery_pct": 90.0},
    {"name": "Mahindra XUV700 (Diesel)", "vehicle_type": "car", "fuel_type": "diesel",
     "tank_capacity": 60.0, "efficiency": 14.0, "current_fuel_pct": 100.0},
    {"name": "Honda Activa (Petrol)", "vehicle_type": "bike", "fuel_type": "petrol",
     "tank_capacity": 5.3, "efficiency": 45.0, "current_fuel_pct": 100.0},
    {"name": "MG ZS EV", "vehicle_type": "car", "fuel_type": "electric",
     "tank_capacity": 50.3, "efficiency": 5.8, "current_fuel_pct": 100.0,
     "battery_capacity_kwh": 50.3, "ev_efficiency": 5.8, "current_battery_pct": 100.0},
]


def seed() -> int:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        if db.query(Vehicle).count() == 0:
            for vd in VEHICLES:
                db.add(Vehicle(**vd, created_at=now, updated_at=now))
            print(f"Seeded {len(VEHICLES)} sample vehicles")
        else:
            print("Vehicles already present - skipping")

        prices = {"petrol": (settings.PETROL_PRICE, "L"), "diesel": (settings.DIESEL_PRICE, "L"),
                  "cng": (settings.CNG_PRICE, "kg"), "electric": (settings.ELECTRICITY_PRICE, "kWh")}
        existing = {p.fuel_type for p in db.query(FuelPrice).all()}
        for ft, (price, unit) in prices.items():
            if ft not in existing:
                db.add(FuelPrice(fuel_type=ft, price_per_unit=price, unit=unit, updated_at=now))
        db.commit()
        print("Seed complete (no facilities are seeded - they come from OpenStreetMap / Open Charge Map).")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(seed())
