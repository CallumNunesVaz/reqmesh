#!/usr/bin/env python3
"""Seed a comprehensive Cessna 172 requirements project with XXXXYYYY UIDs."""

import os, requests, time, sys, re

BASE = "http://localhost:8000/api"
PID = "cessna-172"

# Mutations require an editor/admin token.
_login = requests.post(f"{BASE}/auth/login", json={
    "username": os.environ.get("RT_SEED_USER", "admin"),
    "password": os.environ.get("RT_SEED_PASSWORD", "admin"),
})
if _login.status_code >= 400:
    print(f"Login failed ({_login.status_code}): {_login.text[:200]}")
    sys.exit(1)
HEADERS = {"Authorization": f"Bearer {_login.json()['token']}"}

def post(path, data=None):
    r = requests.post(f"{BASE}{path}", json=data, headers=HEADERS)
    if r.status_code >= 400:
        print(f"  ERROR {r.status_code}: {r.text[:200]}")
        return None
    return r.json() if r.text else {"ok": True}

def put(path, data):
    r = requests.put(f"{BASE}{path}", json=data, headers=HEADERS)
    if r.status_code >= 400:
        print(f"  ERROR {r.status_code}: {r.text[:200]}")
        return None
    return r.json()

def get(path):
    r = requests.get(f"{BASE}{path}", headers=HEADERS)
    if r.status_code >= 400:
        return None
    return r.json()

# Delete existing project
requests.delete(f"{BASE}/projects/{PID}", headers=HEADERS)

# Create project
print("Creating Cessna 172 project...")
r = requests.post(f"{BASE}/projects", json={"id": PID, "name": "Cessna 172S Skyhawk SP"}, headers=HEADERS)
print("  OK")

def req(pid, tid, name, desc, ptype="functional", priority="high", rationale="", source="",
        verification="test", vstatus="pending", baseline=None, allocated="", attrs=None, relations=None):
    return {
        "id": tid, "name": name, "description": desc, "type": ptype, "priority": priority,
        "status": "proposed", "parent": pid, "rationale": rationale, "source": source,
        "verification_method": verification, "verification_status": vstatus,
        "baseline": baseline, "allocated_to": allocated, "attributes": attrs or [],
        "relations": relations or [], "verification_cases": [],
    }

requirements = []

# Top-level groups (groups have 0000 suffix)
requirements.append(req(None, "ACFT0000", "Aircraft System",
  "<p>The complete Cessna 172S Skyhawk SP aircraft system shall comply with FAR Part 23 airworthiness standards.</p>",
  "functional", "critical", "Top-level system requirement", "FAR Part 23", baseline="PDR"))

requirements.append(req("ACFT0000", "AFRM0000", "Airframe",
  "<p>The airframe shall provide structural integrity for all flight and ground loads per FAR 23.301-23.575.</p>",
  "design", "critical", "Structural integrity is fundamental to safety", "FAR 23.301", baseline="PDR"))
requirements.append(req("AFRM0000", "AFRM0001", "Fuselage Structure",
  "<p>The fuselage shall provide a semi-monocoque aluminum structure with four seats and corrosion-resistant skin.</p>",
  "design", "high", "Primary occupant enclosure", "Cessna DS-110"))
requirements.append(req("AFRM0001", "AFRM0002", "Cabin Interior",
  "<p>The cabin shall accommodate 4 occupants with 3-point restraint harnesses and cargo tie-down points.</p>",
  "design", "high", "Occupant safety and comfort", "FAR 23.785"))
requirements.append(req("AFRM0001", "AFRM0003", "Cockpit Layout",
  "<p>The cockpit shall provide ergonomic access to all primary flight controls and instruments visible to both pilots.</p>",
  "design", "high", allocated="Cockpit"))
requirements.append(req("AFRM0000", "AFRM0004", "Wing Assembly",
  "<p>The wings shall provide a high-wing, strut-braced configuration with NACA 2412 airfoil.</p>",
  "design", "critical", "High-wing for stability and visibility", "Cessna DS-120", baseline="PDR"))
requirements.append(req("AFRM0004", "AFRM0005", "Main Spar",
  "<p>The main spar shall withstand ultimate load factor of +3.8g/-1.52g per FAR 23.337.</p>",
  "design", "critical", "Primary load path", "FAR 23.337"))
requirements.append(req("AFRM0004", "AFRM0006", "Wing Fuel Tanks",
  "<p>Each wing shall house integral fuel tanks with total capacity of 56 US gallons (212 L).</p>",
  "design", "high", "Fuel storage per FAR 23.963", "FAR 23.963"))
requirements.append(req("AFRM0000", "AFRM0007", "Empennage",
  "<p>The empennage shall provide conventional tail configuration with horizontal stabilizer and vertical fin.</p>",
  "design", "high", baseline="PDR"))
requirements.append(req("AFRM0007", "AFRM0008", "Horizontal Stabilizer",
  "<p>Provide pitch stability with trim tab for elevator force reduction.</p>", "design", "medium"))
requirements.append(req("AFRM0007", "AFRM0009", "Vertical Fin & Rudder",
  "<p>Provide directional stability and yaw control via rudder.</p>", "design", "medium"))

# Propulsion
requirements.append(req("ACFT0000", "PROP0000", "Propulsion System",
  "<p>The propulsion system shall deliver 180 BHP at 2700 RPM for takeoff and climb performance.</p>",
  "functional", "critical", "Engine performance per type certificate", "Lycoming TCDS", baseline="PDR"))
requirements.append(req("PROP0000", "PROP0001", "Engine",
  "<p>Lycoming IO-360-L2A 4-cylinder, horizontally opposed, air-cooled, fuel-injected engine.</p>",
  "design", "critical", allocated="Engine"))
requirements.append(req("PROP0001", "PROP0002", "Fuel Injection",
  "<p>Precision fuel injection providing optimal mixture across all power settings.</p>", "functional", "high"))
requirements.append(req("PROP0001", "PROP0003", "Ignition System",
  "<p>Dual magneto ignition system providing independent ignition circuits per FAR 33.37.</p>",
  "design", "critical", "Redundancy for safety", "FAR 33.37"))
requirements.append(req("PROP0001", "PROP0004", "Engine Monitoring",
  "<p>Provide tachometer, manifold pressure, CHT, EGT, oil temp and pressure indicators.</p>", "functional", "medium"))
requirements.append(req("PROP0000", "PROP0005", "Propeller",
  "<p>McCauley 2-blade fixed-pitch propeller, 76-inch diameter.</p>", "design", "high", allocated="Propeller"))
requirements.append(req("PROP0000", "PROP0006", "Fuel System",
  "<p>Tank-to-engine fuel delivery with electric boost pump, selector valve, and strainer per FAR 23.955.</p>",
  "functional", "critical", allocated="Fuel System", baseline="CDR"))

# Avionics
requirements.append(req("ACFT0000", "AVNC0000", "Avionics Suite",
  "<p>Garmin G1000 NXi integrated avionics with PFD, MFD, and ADAHRS.</p>",
  "functional", "critical", "Modern glass cockpit standard", "Garmin G1000 NXi", baseline="CDR"))
requirements.append(req("AVNC0000", "AVNC0001", "Primary Flight Display",
  "<p>10.4-inch LCD PFD showing attitude, airspeed, altitude, heading and vertical speed.</p>", "interface", "critical"))
requirements.append(req("AVNC0000", "AVNC0002", "Multi-Function Display",
  "<p>10.4-inch LCD MFD showing moving map, engine data, weather, traffic.</p>", "interface", "high"))
requirements.append(req("AVNC0000", "AVNC0003", "Navigation Systems",
  "<p>Integrated GPS/WAAS, VOR/LOC/GS, with ADS-B In/Out per 14 CFR 91.227.</p>",
  "functional", "critical", "Navigation per regulatory requirements", "14 CFR 91.227"))
requirements.append(req("AVNC0003", "AVNC0004", "GPS Receiver",
  "<p>WAAS-enabled GPS with SBAS providing LPV approach capability.</p>", "functional", "critical"))
requirements.append(req("AVNC0003", "AVNC0005", "VOR/ILS Receiver",
  "<p>VOR/LOC/GS navigation receiver with CDI display.</p>", "functional", "high"))
requirements.append(req("AVNC0000", "AVNC0006", "Communication Systems",
  "<p>Dual VHF COM transceivers (118-137 MHz) with 8.33 kHz channel spacing.</p>",
  "interface", "high", "Communication per ICAO requirements", "ICAO Annex 10"))
requirements.append(req("AVNC0006", "AVNC0007", "VHF COM 1/2",
  "<p>Two independent COM radios with automatic squelch and intercom integration.</p>", "functional", "medium"))
requirements.append(req("AVNC0006", "AVNC0008", "Transponder",
  "<p>Mode S transponder with ADS-B Out and extended squitter per DO-260B.</p>", "functional", "critical", source="DO-260B"))
requirements.append(req("AVNC0006", "AVNC0009", "Audio Panel",
  "<p>GMA 1360 audio panel with marker beacon, intercom, and music input.</p>", "interface", "medium"))

# Flight Controls
requirements.append(req("ACFT0000", "FLTC0000", "Flight Control System",
  "<p>Conventional mechanical flight control system with cable-pulley actuation per FAR 23.671-23.703.</p>",
  "functional", "critical", "Flight control reliability", "FAR 23.671", baseline="PDR"))
requirements.append(req("FLTC0000", "FLTC0001", "Primary Controls",
  "<p>Dual yoke control of ailerons, elevator, rudder with cables and pushrods.</p>", "functional", "critical"))
requirements.append(req("FLTC0001", "FLTC0002", "Aileron Control",
  "<p>Frise-type ailerons with differential throw providing roll control.</p>", "design", "high"))
requirements.append(req("FLTC0001", "FLTC0003", "Elevator Control",
  "<p>Elevator control via push-pull tube with trim tab for pitch trim.</p>", "design", "high"))
requirements.append(req("FLTC0001", "FLTC0004", "Rudder Control",
  "<p>Cable-actuated rudder with ground-adjustable trim tab.</p>", "design", "medium"))
requirements.append(req("FLTC0000", "FLTC0005", "Secondary Controls",
  "<p>Electrically-actuated flaps with 4 position settings (0,10,20,30 degrees).</p>", "functional", "high"))
requirements.append(req("FLTC0005", "FLTC0006", "Flap System",
  "<p>Single-slotted Fowler flaps, electric motor actuation, position indicator on panel.</p>", "design", "high"))
requirements.append(req("FLTC0005", "FLTC0007", "Trim System",
  "<p>Manual pitch trim wheel and electric pitch trim switch on yoke.</p>", "design", "medium"))

# Landing Gear
requirements.append(req("ACFT0000", "LNDG0000", "Landing Gear System",
  "<p>Tricycle fixed gear configuration with steerable nosewheel per FAR 23.471-23.511.</p>",
  "design", "critical", baseline="CDR"))
requirements.append(req("LNDG0000", "LNDG0001", "Main Gear",
  "<p>Tubular spring steel main gear legs with Cleveland wheels and brakes.</p>", "design", "high"))
requirements.append(req("LNDG0000", "LNDG0002", "Nose Gear",
  "<p>Steerable nose gear with shimmy damper and 5.00-5 tire.</p>", "design", "high"))
requirements.append(req("LNDG0000", "LNDG0003", "Braking System",
  "<p>Hydraulic toe brakes on pilot side, single-disc on each main wheel.</p>", "functional", "critical"))

# Electrical
requirements.append(req("ACFT0000", "ELEC0000", "Electrical System",
  "<p>28V DC electrical system with 60A alternator and 24V battery per FAR 23.1351-23.1365.</p>",
  "functional", "critical", baseline="CDR"))
requirements.append(req("ELEC0000", "ELEC0001", "Power Generation",
  "<p>60-amp engine-driven alternator with solid-state voltage regulator.</p>", "design", "high"))
requirements.append(req("ELEC0000", "ELEC0002", "Battery",
  "<p>24V 13.6Ah sealed lead-acid battery providing emergency power for 30 minutes minimum.</p>",
  "design", "critical"))
requirements.append(req("ELEC0000", "ELEC0003", "Distribution",
  "<p>Main and essential bus architecture with circuit breaker protection for all systems.</p>", "design", "high"))
requirements.append(req("ELEC0000", "ELEC0004", "External Power",
  "<p>External power receptacle for GPU connection on ground.</p>", "interface", "low"))

# Environmental
requirements.append(req("ACFT0000", "ENVR0000", "Environmental Control",
  "<p>Cabin environmental system providing heating, ventilation and defrost per FAR 23.831.</p>",
  "functional", "high", baseline="CDR"))
requirements.append(req("ENVR0000", "ENVR0001", "Cabin Heat",
  "<p>Engine exhaust heat exchanger providing cabin heat with cockpit and cabin outlets.</p>", "functional", "high"))
requirements.append(req("ENVR0000", "ENVR0002", "Ventilation",
  "<p>Fresh air vents with adjustable outlets for pilot and co-pilot positions.</p>", "functional", "medium"))
requirements.append(req("ENVR0000", "ENVR0003", "Windshield Defrost",
  "<p>Defroster providing heated air to windshield for ice/fog clearance.</p>", "functional", "critical"))

# Safety
requirements.append(req("ACFT0000", "SAFE0000", "Safety Systems",
  "<p>All safety systems shall meet FAR Part 23 requirements for occupant protection.</p>",
  "functional", "critical", "Safety is paramount", "FAR 23.1300"))
requirements.append(req("SAFE0000", "SAFE0001", "Stall Warning",
  "<p>Pneumatic stall warning horn activating at 5-10 knots above stall speed per FAR 23.207.</p>",
  "functional", "critical", source="FAR 23.207"))
requirements.append(req("SAFE0000", "SAFE0002", "Fire Detection",
  "<p>Engine compartment fire detection with cockpit warning light.</p>", "functional", "critical"))
requirements.append(req("SAFE0000", "SAFE0003", "ELT",
  "<p>406 MHz ELT meeting TSO-C126b requirements with automatic activation on impact.</p>",
  "functional", "critical", source="TSO-C126b"))
requirements.append(req("SAFE0000", "SAFE0004", "Lighting Systems",
  "<p>Navigation, anti-collision, landing/taxi lights per FAR 23.1385-23.1401.</p>", "functional", "high"))

print(f"Defined {len(requirements)} requirements")

print("\nCreating requirements...")
failed = 0
for r in requirements:
    pid = r.pop("parent")
    result = post(f"/projects/{PID}/requirements", r)
    if result is None:
        failed += 1
        continue
    if pid:
        put(f"/projects/{PID}/requirements/{r['id']}", {"parent": pid})
print(f"  Created {len(requirements) - failed} / {len(requirements)} ({failed} failed)")

# Verification cases
vcs = [
    {"id": "VCAF0001", "name": "Structural Static Test", "method": "test", "description": "Static load test of airframe to ultimate load"},
    {"id": "VCPR0001", "name": "Engine Run-Up Test", "method": "test", "description": "Full power engine run at takeoff RPM"},
    {"id": "VCAV0001", "name": "Avionics System Test", "method": "test", "description": "End-to-end avionics suite integration test"},
    {"id": "VCFC0001", "name": "Flight Control Free-Play Check", "method": "inspection", "description": "Control surface free play inspection"},
    {"id": "VCEL0001", "name": "Electrical Load Analysis", "method": "analysis", "description": "Electrical system load analysis under all flight conditions"},
    {"id": "VCFL0001", "name": "Fuel System Flow Test", "method": "test", "description": "Fuel flow test at all attitudes and power settings"},
    {"id": "VCCS0001", "name": "Crashworthiness Analysis", "method": "analysis", "description": "FAR 23.561 emergency landing dynamic analysis"},
]
print("\nCreating verification cases...")
for vc in vcs:
    post(f"/projects/{PID}/verification", vc)

# Link VCs to requirements
vc_links = {
    "VCAF0001": ["AFRM0000"],
    "VCPR0001": ["PROP0001"],
    "VCAV0001": ["AVNC0000"],
    "VCFC0001": ["FLTC0000"],
    "VCEL0001": ["ELEC0000"],
    "VCFL0001": ["PROP0006"],
    "VCCS0001": ["AFRM0001"],
}
for vc_id, req_ids in vc_links.items():
    for rid in req_ids:
        req = get(f"/projects/{PID}/requirements/{rid}")
        if req:
            req["verification_cases"] = list(set(req.get("verification_cases", []) + [vc_id]))
            put(f"/projects/{PID}/requirements/{rid}", {"verification_cases": req["verification_cases"]})
        vc = get(f"/projects/{PID}/verification/{vc_id}")
        if vc:
            vc["verified_requirements"] = list(set(vc.get("verified_requirements", []) + [rid]))
            put(f"/projects/{PID}/verification/{vc_id}", {"verified_requirements": vc["verified_requirements"]})

# Cross-cutting relations
print("\nAdding cross-cutting relations...")
relations = [
    ("AVNC0005", "AVNC0004", "refines"),
    ("FLTC0002", "FLTC0001", "refines"),
    ("FLTC0003", "FLTC0001", "refines"),
    ("FLTC0004", "FLTC0001", "refines"),
    ("FLTC0006", "FLTC0005", "refines"),
    ("AVNC0000", "FLTC0000", "satisfies"),
    ("SAFE0000", "AFRM0000", "derives"),
    ("PROP0006", "ELEC0000", "satisfies"),
]
for src, tgt, rel_type in relations:
    req = get(f"/projects/{PID}/requirements/{src}")
    if req:
        req["relations"] = req.get("relations", []) + [{"type": rel_type, "target": tgt}]
        put(f"/projects/{PID}/requirements/{src}", {"relations": req["relations"]})

# Add traces
print("Adding trace links...")
requests.put(f"{BASE}/projects/{PID}/traces", headers=HEADERS, json={"links": [
    {"source": "ACFT0000", "target": "AFRM0000", "type": "refines"},
    {"source": "ACFT0000", "target": "PROP0000", "type": "refines"},
    {"source": "ACFT0000", "target": "AVNC0000", "type": "refines"},
    {"source": "ACFT0000", "target": "FLTC0000", "type": "refines"},
    {"source": "ACFT0000", "target": "LNDG0000", "type": "refines"},
    {"source": "ACFT0000", "target": "ELEC0000", "type": "refines"},
    {"source": "ACFT0000", "target": "ENVR0000", "type": "refines"},
    {"source": "ACFT0000", "target": "SAFE0000", "type": "refines"},
]})

# Change requests
print("Creating change requests...")
for cr in [
    {"id": "CR000001", "title": "Engine Upgrade", "description": "Evaluate Lycoming IO-390 upgrade for 210 HP", "affected_requirements": ["PROP0001", "PROP0005"]},
    {"id": "CR000002", "title": "Landing Gear Inspection", "description": "Add corrosion inspection interval for spring steel gear legs", "affected_requirements": ["LNDG0001"]},
]:
    requests.post(f"{BASE}/projects/{PID}/change-requests", json=cr, headers=HEADERS)

# Risks
print("Creating risks...")
for r in [
    {"id": "RSK00001", "title": "Engine Failure on Takeoff", "description": "Excessive CHT leading to engine failure at critical phase", "severity": "critical", "probability": "low"},
    {"id": "RSK00002", "title": "Fuel Exhaustion", "description": "Fuel mismanagement or leak leading to fuel exhaustion before destination", "severity": "high", "probability": "medium"},
    {"id": "RSK00003", "title": "Avionics Overheat", "description": "G1000 display failure due to overheating in hot cockpit", "severity": "medium", "probability": "low"},
]:
    requests.post(f"{BASE}/projects/{PID}/risks", json=r, headers=HEADERS)

# Comments
print("Adding comments...")
requests.post(f"{BASE}/projects/{PID}/comments", headers=HEADERS, json={"requirement_id": "AVNC0000", "author": "System Engineer", "text": "G1000 NXi is the latest version - confirm supplier lead time."})
requests.post(f"{BASE}/projects/{PID}/comments", headers=HEADERS, json={"requirement_id": "ACFT0000", "author": "Chief Engineer", "text": "Verify all FAR Part 23 amendments are incorporated."})

print(f"\n=== Cessna 172 seeded ===")
print(f"Project: {PID}")
print(f"Requirements: ~{len(requirements)}")
