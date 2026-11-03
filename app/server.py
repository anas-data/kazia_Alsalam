#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ممر MAMAR — نموذج تشغيلي حيّ لمنصة كازية السلام في منفذ السلامة.

لا تبعيات خارجية: Python 3 مكتبة قياسية فقط + متصفح.
يشغّل واجهة RTL عربية وواجهة REST بسيطة، ويحفظ الحالة في app/data/state.json.

    python3 app/server.py            # ثم افتح http://localhost:3000
    PORT=8080 python3 app/server.py
"""

from __future__ import annotations

import html as html_lib
import json
import os
import random
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "state.json"
LOCK = threading.RLock()
random.seed()

ARABIC_PLATES = ["حلب ٤٤١٢٨", "دمشق ٢١٠٩٧", "إدلب ٨٨٣١٠", "حلب ١٩٧٥٥",
                 "حمص ٣٣٠٤٢", "TR 34 AB 217", "TR 06 TK 908", "حلب ٦٦٧١٩",
                 "اللاذقية ١٢٤٤٨", "TR 27 MN 451", "حلب ٥٠٢٣٣", "TR 01 KD 118"]
DRIVERS = ["أبو خالد", "محمود الحاج", "عبد الرحمن طباخ", "يوسف الشبلي", "أحمد عشاوي",
           "مصطفى كنعان", "سراج الدين", "عمار الحلبي", "خالد الشهابي", "فادي مرعي"]
FLEET_NAMES = ["شركة الشمال للنقل", "أعزاز ترانزيت", "مجموعة الفرات للشحن", "كليس لوجستيك"]


def now() -> datetime:
    return datetime.now()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def minutes_ago(m: int) -> str:
    return iso(now() - timedelta(minutes=m))


def minutes_ahead(m: int) -> str:
    return iso(now() + timedelta(minutes=m))


def hhmm(dt_str: str) -> str:
    try:
        return datetime.fromisoformat(dt_str).strftime("%H:%M")
    except Exception:
        return "--:--"


def new_state() -> dict:
    products = [
        {"id": "diesel", "name": "مازوت أول", "grade": "قياسي", "price": 175,
         "tank": 18400, "capacity": 40000, "kind": "truck", "color": "#f6a623"},
        {"id": "diesel_pro", "name": "مازوت إنتاجي", "grade": "للآليات والشاحنات", "price": 150,
         "tank": 9600, "capacity": 25000, "kind": "truck", "color": "#e07b39"},
        {"id": "b90", "name": "بنزين 90", "grade": "أوكتان 90", "price": 185,
         "tank": 12400, "capacity": 20000, "kind": "car", "color": "#5ac8a8"},
        {"id": "b95", "name": "بنزين 95", "grade": "أوكتان 95", "price": 195,
         "tank": 8100, "capacity": 15000, "kind": "car", "color": "#4a90d9"},
    ]
    lanes = (
        [{"id": f"T{i}", "kind": "truck", "label": f"مسار شاحنات {i}", "status": "idle", "booking_id": None}
         for i in range(1, 5)]
        + [{"id": f"C{i}", "kind": "car", "label": f"مسار سيارات {i}", "status": "idle", "booking_id": None}
           for i in range(1, 3)]
    )
    fleets = [
        {"id": f"F{i+1}", "name": FLEET_NAMES[i], "balance": b, "limit": l,
         "tier": t, "trucks": n, "liters_month": lm}
        for i, (b, l, t, n, lm) in enumerate([
            (28_400_000, 60_000_000, "بلاتيني", 42, 312_000),
            (12_750_000, 30_000_000, "ذهبي", 26, 181_000),
            (6_320_000, 20_000_000, "فضي", 18, 104_000),
            (2_180_000, 12_000_000, "أساسي", 9, 47_000),
        ])
    ]

    bookings: list[dict] = []
    transactions: list[dict] = []
    events: list[dict] = []

    counter = 1041

    def mk(plate, driver, fleet_id, product_id, liters, state, created_min,
           lane_id=None, direction="ترانزيت", done_min=None):
        nonlocal counter
        counter += 1
        p = next(x for x in products if x["id"] == product_id)
        bid = f"KZ-{counter}"
        b = {
            "id": bid, "plate": plate, "driver": driver, "fleet_id": fleet_id,
            "product_id": product_id, "product": p["name"], "liters": liters,
            "price": p["price"], "amount": liters * p["price"],
            "direction": direction, "state": state, "lane_id": lane_id,
            "created_at": minutes_ago(created_min), "called_at": None,
            "started_at": None, "done_at": minutes_ago(done_min) if done_min else None,
            "qr": f"MAMAR|{bid}|{plate}|{liters}|{random.randint(1000, 9999)}",
            "channel": "تطبيق" if fleet_id else "بوابة/كiosk", "no_show": False,
        }
        if state in ("called", "fueling", "done"):
            b["called_at"] = minutes_ago(max(created_min - 4, 1))
        if state in ("fueling", "done"):
            b["started_at"] = minutes_ago(max(created_min - 6, 1))
        bookings.append(b)
        return b

    # حجوزات نشطة
    mk("حلب ٤٤١٢٨", "أبو خالد", "F1", "diesel", 320, "called", 18, "T1", "دخول")
    mk("TR 34 AB 217", "محمود الحاج", "F2", "diesel", 280, "fueling", 22, "T2", "خروج")
    mk("إدلب ٨٨٣١٠", "عبد الرحمن طباخ", None, "diesel_pro", 200, "booked", 14, None, "دخول")
    mk("حلب ١٩٧٥٥", "يوسف الشبلي", "F1", "diesel", 350, "booked", 11, None, "ترانزيت")
    mk("TR 06 TK 908", "سراج الدين", "F3", "diesel", 300, "booked", 9, None, "ترانزيت")
    mk("دمشق ٢١٠٩٧", "أحمد عشاوي", None, "b90", 40, "booked", 7, None, "دخول")
    mk("حلب ٦٦٧١٩", "مصطفى كنعان", "F2", "diesel", 260, "booked", 5, None, "خروج")
    mk("TR 27 MN 451", "خالد الشهابي", "F1", "diesel", 340, "booked", 3, None, "ترانزيت")
    mk("حمص ٣٣٠٤٢", "فادي مرعي", None, "b95", 35, "booked", 2, None, "خروج")

    # حجوزات مكتملة (للمؤشرات والرسوم)
    done_specs = [
        ("حلب ٥٠٢٣٣", "F1", "diesel", 300, 180), ("TR 01 KD 118", "F2", "diesel", 280, 165),
        ("اللاذقية ١٢٤٤٨", None, "b90", 45, 152), ("حلب ٤٤١٢٨", "F1", "diesel", 310, 140),
        ("TR 34 AB 217", "F3", "diesel_pro", 240, 126), ("إدلب ٨٨٣١٠", None, "b95", 40, 111),
        ("دمشق ٢١٠٩٧", "F1", "diesel", 330, 96), ("TR 06 TK 908", "F2", "diesel", 290, 82),
        ("حلب ١٩٧٥٥", None, "b90", 38, 70), ("حلب ٦٦٧١٩", "F3", "diesel", 270, 58),
        ("TR 27 MN 451", "F1", "diesel", 360, 44), ("حمص ٣٣٠٤٢", None, "b95", 42, 31),
        ("حلب ٥٠٢٣٣", "F2", "diesel_pro", 220, 20), ("TR 01 KD 118", None, "b90", 35, 9),
    ]
    for plate, fleet, pid, liters, m in done_specs:
        b = mk(plate, random.choice(DRIVERS), fleet, pid, liters, "done", m + 16, None,
               random.choice(["دخول", "خروج", "ترانزيت"]), m)
        p = next(x for x in products if x["id"] == pid)
        transactions.append({
            "id": "TX-" + b["id"].replace("KZ-", ""), "booking_id": b["id"], "plate": plate,
            "fleet_id": fleet, "product_id": pid, "product": p["name"], "liters": liters,
            "amount": b["amount"], "at": b["done_at"], "method": "محفظة أسطول" if fleet else "نقد/حوالة",
        })

    # اربط المسارات بالحجوزات النشطة التي خُصّصت لها
    for b in bookings:
        if b["lane_id"]:
            lane = next((l for l in lanes if l["id"] == b["lane_id"]), None)
            if lane:
                lane["status"] = "busy" if b["state"] == "fueling" else "reserved"
                lane["booking_id"] = b["id"]

    supply_orders = [
        {"id": "SO-8821", "product_id": "diesel", "product": "مازوت أول", "requested_l": 20000,
         "state": "في الطريق", "created_at": minutes_ago(240), "valid_until": minutes_ahead(3200),
         "eta": minutes_ahead(95), "tanker": "صهريج 34-TK-1180", "note": "معتمد ومحمّل من بانياس"},
        {"id": "SO-8822", "product_id": "diesel_pro", "product": "مازوت إنتاجي", "requested_l": 12000,
         "state": "قيد الاعتماد", "created_at": minutes_ago(95), "valid_until": minutes_ahead(4225),
         "eta": minutes_ahead(430), "tanker": "—", "note": "بانتظار اعتماد المنصة المعتمدة"},
        {"id": "SO-8819", "product_id": "b90", "product": "بنزين 90", "requested_l": 8000,
         "state": "واصل", "created_at": minutes_ago(1500), "valid_until": minutes_ago(1800),
         "eta": minutes_ago(40), "tanker": "صهريج 01-BN-440", "note": "أُفرغ في الخزان"},
    ]

    events = [
        {"id": 1, "at": minutes_ago(2), "actor": "النظام", "type": "حجز", "text": "حجز KZ-1049 • بنزين 95 • 35 لتر"},
        {"id": 2, "at": minutes_ago(9), "actor": "مشغّل المسار", "type": "تعبئة", "text": "إتمام TX-1050 • 35 لتر بنزين 90"},
        {"id": 3, "at": minutes_ago(20), "actor": "النظام", "type": "توريد", "text": "SO-8819 واصل وأُفرغ في خزان بنزين 90"},
        {"id": 4, "at": minutes_ago(40), "actor": "المدير", "type": "تسعيرة", "text": "اعتماد نشرة الأسعار رقم 2026/41"},
        {"id": 5, "at": minutes_ago(95), "actor": "النظام", "type": "توريد", "text": "إنشاء SO-8822 • صلاحية الرابط 72 ساعة"},
    ]

    return {
        "version": 1,
        "meta": {"station": "كازية السلام", "border": "منفذ السلامة — باب السلامة / أعزاز",
                 "platform": "ممر MAMAR", "bulletin": "2026/41", "shift": "الوردية الصباحية"},
        "settings": {"safety_buffer": 0.08, "slot_minutes": 15, "quota_per_plate": 400,
                     "priority_fee": 2000, "margin": 12, "baseline_wait_min": 240,
                     "trucks_day": 191, "passengers_day": 5075, "vehicles_day": 1500,
                     "capture_trucks": 0.30, "capture_cars": 0.10,
                     "liters_truck": 220, "liters_car": 35, "saas_fee": 2_500_000},
        "products": products, "lanes": lanes, "fleets": fleets,
        "bookings": bookings, "transactions": transactions,
        "supply_orders": supply_orders, "events": events,
        "counter": counter, "ticks": 0,
        "hourly": [6, 9, 14, 22, 31, 28, 19, 24],  # آلاف اللترات لآخر 8 ساعات (توضيحي)
    }


def load_state() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                s = json.load(f)
            if s.get("version") == 1:
                return s
        except Exception:
            pass
    s = new_state()
    save_state(s)
    return s


def save_state(s: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


STATE = load_state()


def log_event(s, actor, etype, text):
    s["events"].insert(0, {"id": int(time.time() * 1000), "at": iso(now()),
                           "actor": actor, "type": etype, "text": text})
    s["events"] = s["events"][:60]


def product(s, pid):
    return next((p for p in s["products"] if p["id"] == pid), None)


def booking(s, bid):
    return next((b for b in s["bookings"] if b["id"] == bid), None)


def next_id(s, prefix="KZ"):
    s["counter"] += 1
    return f"{prefix}-{s['counter']}"


def confirmed_inbound(s, pid):
    return sum(o["requested_l"] for o in s["supply_orders"]
               if o["product_id"] == pid and o["state"] in ("معتمد", "محمّل", "في الطريق"))


def reserved_liters(s, pid):
    return sum(b["liters"] for b in s["bookings"]
               if b["product_id"] == pid and b["state"] in ("booked", "called", "fueling"))


def availability(s, pid):
    p = product(s, pid)
    if not p:
        return 0
    buffer = p["capacity"] * s["settings"]["safety_buffer"]
    return int(max(0, p["tank"] + confirmed_inbound(s, pid) - reserved_liters(s, pid) - buffer))


def compute_metrics(s):
    done = [b for b in s["bookings"] if b["state"] == "done"]
    waits = []
    for b in done:
        try:
            a = datetime.fromisoformat(b["created_at"])
            z = datetime.fromisoformat(b["done_at"])
            waits.append(max(1, (z - a).total_seconds() / 60))
        except Exception:
            pass
    avg_wait = round(sum(waits) / len(waits), 1) if waits else 0
    liters = sum(t["liters"] for t in s["transactions"])
    revenue = sum(t["amount"] for t in s["transactions"])
    active = [b for b in s["bookings"] if b["state"] in ("booked", "called", "fueling")]
    cancelled = [b for b in s["bookings"] if b["state"] in ("cancelled", "expired")]
    fulfil = round(100 * len(done) / max(1, len(done) + len(cancelled)), 1)
    baseline = s["settings"]["baseline_wait_min"]
    reduction = round(100 * (1 - avg_wait / baseline), 1) if avg_wait else 0
    util = round(100 * sum(1 for l in s["lanes"] if l["status"] != "idle") / len(s["lanes"]))
    return {
        "avg_wait_min": avg_wait, "baseline_wait_min": baseline, "wait_reduction_pct": max(0, reduction),
        "liters_today": liters, "revenue_today": revenue, "served": len(done),
        "active": len(active), "cancelled": len(cancelled), "fulfilment_pct": fulfil,
        "utilization_pct": util, "no_show_pct": 2.1,
        "tank_total": sum(p["tank"] for p in s["products"]),
        "tank_capacity": sum(p["capacity"] for p in s["products"]),
        "contracted_liters_pct": 61,
    }


def public_state(s):
    out = dict(s)
    out["metrics"] = compute_metrics(s)
    out["availability"] = {p["id"]: availability(s, p["id"]) for p in s["products"]}
    out["server_time"] = iso(now())
    return out


# ---------------------------------------------------------------------------
# العمليات
# ---------------------------------------------------------------------------

def create_booking(data: dict):
    with LOCK:
        s = STATE
        plate = str(data.get("plate", "")).strip()
        pid = str(data.get("product_id", "diesel"))
        p = product(s, pid)
        if not plate or not p:
            return {"ok": False, "error": "رقم اللوحة أو نوع المحروقات غير صحيح"}
        try:
            liters = int(data.get("liters", 0))
        except Exception:
            return {"ok": False, "error": "الكمية غير صحيحة"}
        if liters < 10 or liters > s["settings"]["quota_per_plate"]:
            return {"ok": False, "error": f"الكمية يجب أن تكون بين 10 و {s['settings']['quota_per_plate']} لتر"}
        dup = next((b for b in s["bookings"]
                    if b["plate"] == plate and b["state"] in ("booked", "called", "fueling")), None)
        if dup:
            return {"ok": False, "error": f"يوجد حجز نشط بالفعل لهذه اللوحة: {dup['id']}"}
        avail = availability(s, pid)
        if liters > avail:
            return {"ok": False,
                    "error": f"الكمية المضمونة المتاحة حالياً {avail:,} لتر فقط. قلّل الكمية أو اختر نافذة لاحقة."}
        fleet_id = data.get("fleet_id") or None
        fleet = next((f for f in s["fleets"] if f["id"] == fleet_id), None) if fleet_id else None
        fee = s["settings"]["priority_fee"] if data.get("priority") else 0
        amount = liters * p["price"] + fee
        if fleet and fleet["balance"] + fleet["limit"] < amount:
            return {"ok": False, "error": "السقف الائتماني للأسطول لا يغطي العملية"}
        bid = next_id(s)
        b = {
            "id": bid, "plate": plate,
            "driver": str(data.get("driver", "")).strip() or "سائق",
            "fleet_id": fleet_id, "product_id": pid, "product": p["name"],
            "liters": liters, "price": p["price"], "amount": amount,
            "direction": str(data.get("direction", "ترانزيت")),
            "state": "booked", "lane_id": None,
            "created_at": iso(now()), "called_at": None, "started_at": None, "done_at": None,
            "qr": f"MAMAR|{bid}|{plate}|{liters}|{random.randint(1000, 9999)}",
            "channel": str(data.get("channel", "تطبيق")), "no_show": False,
            "priority": bool(data.get("priority")),
        }
        s["bookings"].insert(0, b)
        log_event(s, "السائق", "حجز", f"{bid} • {plate} • {liters} لتر {p['name']}" +
                  (" • أولوية" if fee else ""))
        save_state(s)
        return {"ok": True, "booking": b, "state": public_state(s)}


def transition(bid: str, action: str, payload: dict | None = None):
    payload = payload or {}
    with LOCK:
        s = STATE
        b = booking(s, bid)
        if not b:
            return {"ok": False, "error": "الحجز غير موجود"}
        st = b["state"]

        if action == "call":
            if st != "booked":
                return {"ok": False, "error": "يمكن استدعاء الحجوزات بحالة «محجوز» فقط"}
            p = product(s, b["product_id"])
            kind = p["kind"] if p["kind"] == "truck" else "car"
            lanes = [l for l in s["lanes"] if l["status"] == "idle" and l["kind"] == kind]
            if not lanes:
                lanes = [l for l in s["lanes"] if l["status"] == "idle"]
            if not lanes:
                return {"ok": False, "error": "لا يوجد مسار شاغر حالياً"}
            lane = lanes[0]
            lane["status"] = "reserved"
            lane["booking_id"] = bid
            b["state"] = "called"
            b["lane_id"] = lane["id"]
            b["called_at"] = iso(now())
            log_event(s, "المشغّل", "استدعاء", f"{bid} → {lane['label']}")

        elif action == "start":
            if st != "called":
                return {"ok": False, "error": "يجب استدعاء الحجز وتخصيص مسار أولاً"}
            lane = next((l for l in s["lanes"] if l["id"] == b["lane_id"]), None)
            if lane:
                lane["status"] = "busy"
            b["state"] = "fueling"
            b["started_at"] = iso(now())
            log_event(s, "المشغّل", "تعبئة", f"بدء تعبئة {bid} بعد تحقق QR")

        elif action == "complete":
            if st not in ("fueling", "called"):
                return {"ok": False, "error": "الحجز ليس قيد التعبئة"}
            p = product(s, b["product_id"])
            actual = int(payload.get("actual_l", b["liters"]))
            if actual <= 0 or actual > p["tank"]:
                return {"ok": False, "error": "الكمية الفعلية غير منطقية مقابل الخزان"}
            b["liters"] = actual
            b["amount"] = actual * b["price"] + (s["settings"]["priority_fee"] if b.get("priority") else 0)
            p["tank"] = max(0, p["tank"] - actual)
            b["state"] = "done"
            b["done_at"] = iso(now())
            b["started_at"] = b["started_at"] or iso(now())
            lane = next((l for l in s["lanes"] if l["id"] == b["lane_id"]), None)
            if lane:
                lane["status"] = "idle"
                lane["booking_id"] = None
            fleet = next((f for f in s["fleets"] if f["id"] == b["fleet_id"]), None) if b["fleet_id"] else None
            if fleet:
                fleet["balance"] = max(0, fleet["balance"] - b["amount"])
            s["transactions"].insert(0, {
                "id": "TX-" + bid.replace("KZ-", ""), "booking_id": bid, "plate": b["plate"],
                "fleet_id": b["fleet_id"], "product_id": b["product_id"], "product": p["name"],
                "liters": actual, "amount": b["amount"], "at": b["done_at"],
                "method": "محفظة أسطول" if fleet else "نقد/حوالة",
            })
            if s["hourly"]:
                s["hourly"][-1] = round(s["hourly"][-1] + actual / 1000, 1)
            log_event(s, "المشغّل", "إتمام", f"{bid} • {actual} لتر • {b['amount']:,} ل.س")

        elif action == "cancel":
            if st == "done":
                return {"ok": False, "error": "لا يمكن إلغاء حجز مكتمل"}
            b["state"] = "cancelled"
            b["done_at"] = iso(now())
            lane = next((l for l in s["lanes"] if l["id"] == b["lane_id"]), None)
            if lane:
                lane["status"] = "idle"
                lane["booking_id"] = None
            log_event(s, payload.get("actor", "المشغّل"), "إلغاء", f"{bid} • {payload.get('reason', 'بدون سبب')}")
        else:
            return {"ok": False, "error": "إجراء غير معروف"}

        save_state(s)
        return {"ok": True, "booking": b, "state": public_state(s)}


def call_next():
    with LOCK:
        s = STATE
        waiting = [b for b in s["bookings"] if b["state"] == "booked"]
        waiting.sort(key=lambda b: (not b.get("priority", False), b["created_at"]))
        for b in waiting[:6]:
            r = transition(b["id"], "call")
            if r.get("ok"):
                return r
        return {"ok": False, "error": "لا يوجد حجز بانتظار مسار شاغر", "state": public_state(s)}


def update_price(data):
    with LOCK:
        s = STATE
        p = product(s, str(data.get("product_id", "")))
        try:
            price = float(data.get("price", 0))
        except Exception:
            price = 0
        if not p or price <= 0:
            return {"ok": False, "error": "بيانات التسعيرة غير صحيحة"}
        old = p["price"]
        p["price"] = price
        log_event(s, "المدير", "تسعيرة", f"{p['name']}: {old:,} ← {price:,} ل.س/لتر (نشرة جديدة)")
        save_state(s)
        return {"ok": True, "state": public_state(s)}


def refill(data):
    with LOCK:
        s = STATE
        p = product(s, str(data.get("product_id", "")))
        if not p:
            return {"ok": False, "error": "المنتج غير موجود"}
        liters = int(data.get("liters", 8000))
        p["tank"] = min(p["capacity"], p["tank"] + liters)
        log_event(s, "التوريد", "توريد", f"وصول {liters:,} لتر {p['name']} → الخزان {p['tank']:,} لتر")
        save_state(s)
        return {"ok": True, "state": public_state(s)}


def create_supply_order(data):
    with LOCK:
        s = STATE
        p = product(s, str(data.get("product_id", "diesel")))
        if not p:
            return {"ok": False, "error": "المنتج غير موجود"}
        liters = int(data.get("liters", 12000))
        oid = next_id(s, "SO")
        o = {"id": oid, "product_id": p["id"], "product": p["name"], "requested_l": liters,
             "state": "قيد الاعتماد", "created_at": iso(now()),
             "valid_until": minutes_ahead(72 * 60), "eta": minutes_ahead(60 * 8),
             "tanker": "—", "note": "مُولّد آلياً من توقّع الطلب • صلاحية الرابط 72 ساعة"}
        s["supply_orders"].insert(0, o)
        log_event(s, "النظام", "توريد", f"إنشاء {oid} • {liters:,} لتر {p['name']}")
        save_state(s)
        return {"ok": True, "order": o, "state": public_state(s)}


def tick(auto=False):
    with LOCK:
        s = STATE
        s["ticks"] += 1
        # تقدّم أوامر التوريد
        flow = ["قيد الاعتماد", "معتمد", "محمّل", "في الطريق", "واصل"]
        for o in s["supply_orders"]:
            if o["state"] in flow[:-1] and s["ticks"] % 3 == 0:
                o["state"] = flow[flow.index(o["state"]) + 1]
                o["note"] = "تحديث تلقائي من منصة التوريد المعتمدة"
                if o["state"] == "واصل":
                    p = product(s, o["product_id"])
                    if p:
                        p["tank"] = min(p["capacity"], p["tank"] + o["requested_l"])
                    o["tanker"] = "صهريج " + str(random.randint(1000, 9999))
                    log_event(s, "التوريد", "توريد", f"{o['id']} واصل → تفريغ {o['requested_l']:,} لتر")
        # وصول مركبات جديدة
        if s["ticks"] % 2 == 0 and len([b for b in s["bookings"] if b["state"] == "booked"]) < 10:
            pid = random.choice(["diesel", "diesel", "diesel", "diesel_pro", "b90", "b95"])
            fleet_id = random.choice(["F1", "F2", "F3", None, None])
            liters = random.randint(220, 360) if pid in ("diesel", "diesel_pro") else random.randint(25, 45)
            create_booking({"plate": random.choice(ARABIC_PLATES), "driver": random.choice(DRIVERS),
                            "fleet_id": fleet_id, "product_id": pid, "liters": liters,
                            "direction": random.choice(["دخول", "خروج", "ترانزيت"]),
                            "channel": random.choice(["تطبيق", "واتساب", "kiosk", "USSD"])})
        # تشغيل تلقائي للمسارات (اختياري، لإبقاء اللوحة حيّة)
        if auto:
            idle = [l for l in s["lanes"] if l["status"] == "idle"]
            if idle:
                call_next()
            for b in list(s["bookings"]):
                if b["state"] == "called":
                    transition(b["id"], "start")
                elif b["state"] == "fueling":
                    transition(b["id"], "complete")
        # انتهاء صلاحية الحجوزات القديمة (no-show)
        for b in s["bookings"]:
            if b["state"] == "booked":
                try:
                    age = (now() - datetime.fromisoformat(b["created_at"])).total_seconds() / 60
                    if age > 45:
                        b["state"] = "expired"
                        b["done_at"] = iso(now())
                except Exception:
                    pass
        save_state(s)
        return {"ok": True, "state": public_state(s)}


def reset():
    global STATE
    with LOCK:
        STATE = new_state()
        save_state(STATE)
        return {"ok": True, "state": public_state(STATE)}


# ---------------------------------------------------------------------------
# خادم HTTP
# ---------------------------------------------------------------------------

MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
        ".ico": "image/x-icon", ".woff2": "font/woff2"}


class Handler(BaseHTTPRequestHandler):
    server_version = "MAMAR/0.1"

    def log_message(self, fmt, *args):
        if os.environ.get("MAMAR_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not cache:
            self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._json({"ok": True, "service": "ممر MAMAR", "time": iso(now())})
        if path == "/api/state":
            with LOCK:
                return self._json(public_state(STATE))
        if path.startswith("/docs/"):
            docs = ROOT.parent / "docs"
            names = {"01": "01-الفكرة-والجدوى.md", "02": "02-المعمارية-وخارطة-الطريق-التقنية.md"}
            slug = path.rstrip("/").split("/")[-1]
            fname = names.get(slug)
            f = (docs / fname) if fname else None
            if f and f.is_file():
                text = f.read_text(encoding="utf-8")
                page = (
                    '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
                    '<title>ممر — المستند</title><style>'
                    'body{background:#0b1119;color:#dbe5ee;font-family:"Segoe UI",Tahoma,sans-serif;'
                    'padding:28px;line-height:2}'
                    'pre{white-space:pre-wrap;word-wrap:break-word;font-family:inherit;font-size:13.5px;'
                    'max-width:1000px;margin:0 auto;background:#131d28;border:1px solid rgba(255,255,255,.09);'
                    'border-radius:16px;padding:26px}'
                    'h1{color:#f6a623;font-size:19px;margin:0 0 18px}'
                    '</style></head><body><h1>ممر MAMAR · مستند الفكرة</h1><pre>'
                    + html_lib.escape(text) + '</pre></body></html>'
                )
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return self._send(404, "المستند غير موجود".encode("utf-8"), "text/plain; charset=utf-8")
        # ملفات ثابتة
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (PUBLIC / rel).resolve()
        if not str(target).startswith(str(PUBLIC.resolve())) or not target.is_file():
            return self._send(404, "غير موجود".encode("utf-8"), "text/plain; charset=utf-8")
        return self._send(200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream"))

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            data = {}

        if path == "/api/bookings":
            result = create_booking(data)
            return self._json(result, 201 if result.get("ok") else 400)
        if path.startswith("/api/bookings/") and path.endswith("/call"):
            return self._json(transition(path.split("/")[3], "call", data))
        if path.startswith("/api/bookings/") and path.endswith("/start"):
            return self._json(transition(path.split("/")[3], "start", data))
        if path.startswith("/api/bookings/") and path.endswith("/complete"):
            return self._json(transition(path.split("/")[3], "complete", data))
        if path.startswith("/api/bookings/") and path.endswith("/cancel"):
            return self._json(transition(path.split("/")[3], "cancel", data))
        if path == "/api/queue/call-next":
            return self._json(call_next())
        if path == "/api/prices":
            return self._json(update_price(data))
        if path.startswith("/api/tanks/") and path.endswith("/refill"):
            return self._json(refill({"product_id": path.split("/")[3], **data}))
        if path == "/api/supply-orders":
            return self._json(create_supply_order(data))
        if path == "/api/tick":
            return self._json(tick(bool(data.get("auto"))))
        if path == "/api/reset":
            return self._json(reset())
        return self._json({"ok": False, "error": "مسار غير معروف"}, 404)


def main():
    port = int(os.environ.get("PORT", "3000"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    print(f"ممر MAMAR جاهز على http://0.0.0.0:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
