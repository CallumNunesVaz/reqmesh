"""Cessna 172S Skyhawk SP demo project — comprehensive example exercising all
reqmesh features (traceability, coverage, fingerprints, quality, planning).

Writes through YamlStore directly — no running server or credentials needed.
Runs at first launch when the data root has no projects (see ``lifespan`` in
app.main).  Disable via ``RT_SEED_DEMO=false``.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.services.yaml_store import YamlStore

PROJECT_ID = "cessna-172"
PROJECT_NAME = "Cessna 172S Skyhawk SP"


# ── helpers ───────────────────────────────────────────────────────────────────

def _req(pid, tid, name, desc, ptype="functional", status="proposed",
         priority="high", rationale="", source="", verification="test",
         baseline=None, allocated="", effort=None, priorities=None,
         needs=None, derived=False, normative=True,
         references=None, reviewed=None):
    return {
        "id": tid,
        "name": name,
        "description": desc,
        "type": ptype,
        "status": status,
        "priority": priority,
        "parent": pid,
        "rationale": rationale,
        "source": source,
        "verification_method": verification,
        "verification_status": "pending",
        "baseline": baseline,
        "allocated_to": allocated,
        "cascade_from": None,
        "attributes": [],
        "relations": [],
        "verification_cases": [],
        "references": references or [],
        "needs": needs or [],
        "derived": derived,
        "normative": normative,
        "effort": effort,
        "priorities": priorities or {},
        "reviewed": reviewed,
    }


def _add_attr(req, key, value):
    req["attributes"].append({"key": key, "value": value})


# ── requirements ──────────────────────────────────────────────────────────────

def _requirements() -> list[dict]:
    r: list[dict] = []

    # ═══════════════════════════════════════════════════════════════════════════
    # TOP-LEVEL — Aircraft System
    # ═══════════════════════════════════════════════════════════════════════════

    r.append(_req(
        None, "ACFT0000",
        "Aircraft System",
        "<p>The complete Cessna 172S Skyhawk SP shall comply with"
        " FAR Part 23 airworthiness standards and deliver predictable,"
        " stable flight characteristics suitable for primary training"
        " and personal transportation.</p>",
        "functional", "approved", "critical",
        "Top-level system requirement defining the product scope for"
        " a 4-seat, single-engine, high-wing trainer.",
        "FAR Part 23 Amendment 64",
        baseline="PDR",
        needs=["design"],
        effort=100,
        priorities={"development": 10, "customers": 10, "safety": 10},
    ))

    # ════════════════════════════════════════════════════════════
    # AIRFRAME SUBSYSTEM
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "AFRM0000",
        "Airframe",
        "<p>The airframe shall provide structural integrity for all"
        " flight and ground loads per FAR 23.301 through 23.575,"
        " with a semi-monocoque aluminum construction and corrosion-resistant"
        " alclad skin.</p>",
        "design", "approved", "critical",
        "Structural integrity is the fundamental safety foundation"
        " of the aircraft. The Cessna 172S uses proven aluminum"
        " semi-monocoque construction for optimal strength-to-weight.",
        "FAR 23.301, Cessna DS-100",
        baseline="PDR",
        allocated="Airframe Team",
        needs=["design", "verification_case"],
        effort=60,
        priorities={"development": 5, "safety": 10, "customers": 3},
    ))

    r.append(_req(
        "AFRM0000", "AFRM0001",
        "Fuselage Structure",
        "<p>The fuselage shall be a semi-monocoque aluminum alloy"
        " structure with four ergonomic seats, two forward-hinged"
        " cabin doors, and a cargo area rated for 120 lb behind"
        " the rear seats.</p>",
        "design", "approved", "high",
        "Primary occupant enclosure must withstand crash loads"
        " per FAR 23.561 while remaining lightweight.",
        "Cessna DS-110",
        allocated="Structures",
        needs=["design"],
        effort=20,
        priorities={"development": 3, "safety": 5, "customers": 5},
    ))

    r.append(_req(
        "AFRM0001", "AFRM0002",
        "Cabin Interior & Restraints",
        "<p>The cabin shall accommodate 4 occupants with 3-point"
        " inertial-reel restraint harnesses for forward seats and"
        " fixed 3-point harnesses for rear seats. Cargo tie-down"
        " points shall withstand 9g forward loading.</p>",
        "design", "approved", "high",
        "Occupant safety during emergency landing is paramount."
        " 3-point harnesses reduce HIC (Head Injury Criterion)"
        " vs lap belts alone.",
        "FAR 23.561, FAR 23.785",
        needs=["design", "verification_case"],
        effort=5,
        priorities={"development": 2, "safety": 8, "customers": 5},
    ))

    r.append(_req(
        "AFRM0001", "AFRM0003",
        "Cockpit Ergonomic Layout",
        "<p>The cockpit shall provide the pilot with unobstructed"
        " access to all primary flight controls, with both PFD and"
        " MFD visible within the pilot's primary field of view"
        " (within 30 degrees of the forward sight line). All"
        " secondary controls (flaps, trim, fuel selector, mixture)"
        " shall be reachable without releasing the yoke.</p>",
        "design", "approved", "high",
        "Training aircraft cockpits must minimize pilot workload."
        " The Cessna 172 tradition places flap switch and trim"
        " wheel within reach of the right hand while the left"
        " hand remains on the yoke.",
        "GAMA Publication 10, Cessna DR-420",
        allocated="Cockpit Integration",
        needs=["design"],
        effort=8,
        priorities={"development": 3, "customers": 8, "safety": 4},
    ))

    r.append(_req(
        "AFRM0000", "AFRM0004",
        "Wing Assembly",
        "<p>The wings shall be a high-wing, strut-braced configuration"
        " using NACA 2412 airfoil with 36 ft span and 174 sq ft"
        " area. The high-wing placement shall provide excellent"
        " downward visibility for the crew and inherent lateral"
        " stability through dihedral effect.</p>",
        "design", "approved", "critical",
        "The high-wing configuration is a defining Cessna 172"
        " characteristic. It provides natural roll stability"
        " (pendulum effect), protects the cabin from sun/rain,"
        " and gives pilots exceptional ground visibility.",
        "Cessna DS-120",
        baseline="PDR",
        needs=["design", "verification_case"],
        effort=25,
        priorities={"development": 5, "safety": 5, "customers": 6},
    ))

    r.append(_req(
        "AFRM0004", "AFRM0005",
        "Main Spar Ultimate Load",
        "<p>The main spar shall withstand an ultimate load factor of"
        " +3.8g and -1.52g with no permanent deformation, per"
        " FAR 23.337 limit maneuvering loads. Safety factor of 1.5"
        " shall be applied to limit loads for ultimate design.</p>",
        "design", "approved", "critical",
        "The main spar is the single most critical structural"
        " element. Failure is catastrophic. The 3.8g limit"
        " corresponds to the Normal Category envelope.",
        "FAR 23.337, FAR 23.305",
        needs=["verification_case"],
        effort=10,
        priorities={"development": 3, "safety": 10},
    ))

    r.append(_req(
        "AFRM0004", "AFRM0006",
        "Integral Wing Fuel Tanks",
        "<p>Each wing shall house an integral fuel tank formed by"
        " the wing structure, sealed with polysulfide sealant,"
        " with total usable capacity of 53 US gallons (200 L)"
        " and 3 gallons unusable. Fuel quantity transmitters"
        " shall be resistive float-type per FAR 23.1337.</p>",
        "design", "approved", "high",
        "Integral (wet-wing) tanks eliminate separate bladder"
        " weight. 53 usable gallons provide ~5 hours endurance"
        " at 75% power with VFR reserves.",
        "FAR 23.963, Cessna DS-121",
        allocated="Fuel Systems",
        needs=["design", "verification_case"],
        effort=8,
        priorities={"development": 3, "safety": 5, "customers": 4},
    ))

    r.append(_req(
        "AFRM0000", "AFRM0007",
        "Empennage",
        "<p>The empennage shall use a conventional tail arrangement"
        " with a fixed horizontal stabilizer plus movable elevator"
        " for pitch control, and a fixed vertical fin plus movable"
        " rudder for directional (yaw) control.</p>",
        "design", "approved", "high",
        baseline="PDR",
        needs=["design"],
        effort=12,
        priorities={"development": 3, "safety": 4, "customers": 2},
    ))

    r.append(_req(
        "AFRM0007", "AFRM0008",
        "Horizontal Stabilizer & Elevator",
        "<p>The horizontal stabilizer shall provide static pitch"
        " stability (positive dCm/dα). The elevator shall be"
        " aerodynamically balanced with a ground-adjustable trim"
        " tab for stick-force reduction. Control forces shall"
        " not exceed 10 lb at V_A.</p>",
        "design", "approved", "medium",
        needs=["design", "verification_case"],
        effort=6,
        priorities={"development": 2, "safety": 3},
    ))

    r.append(_req(
        "AFRM0007", "AFRM0009",
        "Vertical Fin & Rudder",
        "<p>The vertical fin shall provide static directional"
        " stability (positive Cnβ). The rudder shall be"
        " aerodynamically balanced with a ground-adjustable"
        " trim tab. Pedal forces shall not exceed 50 lb at V_A.</p>",
        "design", "approved", "medium",
        needs=["design"],
        effort=5,
        priorities={"development": 2, "safety": 3},
    ))

    # ════════════════════════════════════════════════════════════
    # PROPULSION SUBSYSTEM
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "PROP0000",
        "Propulsion System",
        "<p>The propulsion system shall deliver a minimum of 180 BHP"
        " at 2700 RPM for takeoff and climb performance, meeting"
        " the Lycoming IO-360-L2A type certificate data sheet"
        " specifications.</p>",
        "functional", "approved", "critical",
        "The IO-360-L2A was selected over the carbureted O-360 for"
        " better fuel distribution, no carburetor icing risk, and"
        " improved hot-start behavior. The 180 BHP rating provides"
        " a power loading of 14.2 lb/BHP at MTOW.",
        "Lycoming TCDS E-2918",
        baseline="PDR",
        allocated="Powerplant Team",
        needs=["design", "verification_case"],
        effort=40,
        priorities={"development": 5, "safety": 8, "customers": 5, "maintenance": 4},
    ))

    r.append(_req(
        "PROP0000", "PROP0001",
        "Engine — Lycoming IO-360-L2A",
        "<p>A 4-cylinder, horizontally opposed, air-cooled,"
        " fuel-injected engine with 360 cubic inch displacement,"
        " 8.5:1 compression ratio, and dual magneto ignition."
        " TBO shall be 2000 hours.</p>",
        "design", "approved", "critical",
        "The IO-360 series has over 55,000 units in service."
        " Horizontally opposed configuration minimizes frontal"
        " area and provides natural primary balance.",
        "Lycoming IO-360 Operator's Manual",
        allocated="Engine Integration",
        needs=["design", "verification_case"],
        effort=15,
        priorities={"development": 3, "safety": 8, "maintenance": 5},
    ))

    r.append(_req(
        "PROP0001", "PROP0002",
        "Precision Fuel Injection",
        "<p>The fuel injection system shall deliver a stoichiometric"
        " air-fuel mixture (14.7:1 ± 0.5) across the operating"
        " range from idle (600 RPM) to full power (2700 RPM),"
        " with mixture control adjustable by the pilot via a"
        " vernier control cable.</p>",
        "functional", "approved", "high",
        "Precision fuel injection eliminates the carburetor icing"
        " hazard and provides cylinder-to-cylinder mixture balance"
        " within 0.5 GPH, improving efficiency and reducing CHT"
        " spread.",
        "Lycoming Service Instruction 1427",
        needs=["design"],
        effort=8,
        priorities={"development": 3, "safety": 6, "maintenance": 2},
    ))

    r.append(_req(
        "PROP0001", "PROP0003",
        "Dual Magneto Ignition",
        "<p>Two independent magnetos (Slick 4370/4371 or Bendix"
        " S4LN-20/S4LN-21), each firing one spark plug per"
        " cylinder, shall provide redundant ignition circuits."
        " The left magneto shall fire the bottom plugs; the right"
        " magneto shall fire the top plugs.</p>",
        "design", "approved", "critical",
        "Dual ignition provides both safety redundancy (engine"
        " continues running if one magneto fails) and combustion"
        " efficiency (twin-flame-front propagation reduces burn"
        " time by ~20%, yielding more complete combustion and"
        " ~3% power gain vs single ignition).  Magneto choice"
        " over electronic ignition preserves electrical-system-"
        " independence: the engine runs even with total electrical"
        " failure.",
        "FAR 33.37, Lycoming Service Instruction 1148",
        needs=["design", "verification_case"],
        effort=10,
        priorities={"development": 3, "safety": 10},
    ))

    r.append(_req(
        "PROP0001", "PROP0004",
        "Engine Instrumentation",
        "<p>The engine instrument group shall display: tachometer"
        " (0-3500 RPM), manifold pressure (10-35 inHg), cylinder"
        " head temperature per cylinder (°F), exhaust gas"
        " temperature per cylinder (°F), oil temperature"
        " (75-245°F), and oil pressure (20-115 PSI). All"
        " parameters shall be displayed on the G1000 MFD"
        " engine page with exceedance alerting.</p>",
        "functional", "approved", "medium",
        "Per-cylinder CHT/EGT enables lean-of-peak operation and"
        " early detection of cylinder problems.  The G1000's"
        " engine page replaces individual analog gauges, reducing"
        " panel clutter and pilot scan workload.",
        "Garmin G1000 NXi Engine Indication",
        allocated="Avionics Integration",
        needs=["design"],
        effort=5,
        priorities={"development": 2, "customers": 5, "maintenance": 6},
    ))

    r.append(_req(
        "PROP0000", "PROP0005",
        "Propeller — McCauley 1A170/E",
        "<p>A McCauley 2-blade fixed-pitch aluminium-alloy propeller,"
        " 76-inch diameter, with a pitch of 60 inches (climb"
        " optimised).  The propeller shall produce a static thrust"
        " of at least 550 lbf at sea level, ISA conditions.</p>",
        "design", "approved", "high",
        "Fixed-pitch propeller is simpler, lighter, and cheaper"
        " than constant-speed, suiting the training/rental market."
        "  The 76-inch diameter is the maximum for ground clearance"
        " on the tricycle-gear 172, and the 60-inch pitch provides"
        " a good climb/cruise compromise for the 180 BHP engine.",
        "McCauley TCDS P-874",
        allocated="Powerplant",
        needs=["verification_case"],
        effort=5,
        priorities={"development": 2, "customers": 6, "safety": 3},
    ))

    r.append(_req(
        "PROP0000", "PROP0006",
        "Fuel Delivery System",
        "<p>Fuel shall flow from either wing tank via a 3-position"
        " selector valve (LEFT / RIGHT / OFF) through an electric"
        " auxiliary boost pump, a gascolator strainer, and an"
        " engine-driven diaphragm pump to the fuel injection"
        " servo.  The electric boost pump shall be used for"
        " engine start, takeoff, landing, and as backup for"
        " the engine-driven pump below 2000 ft AGL.  Fuel flow"
        " rate shall not fall below 14 GPH at full power.</p>",
        "functional", "approved", "critical",
        "The electric boost pump provides critical redundancy"
        " during high-risk phases (takeoff/landing) and serves"
        " as a backup if the engine-driven pump fails.  The"
        " gascolator captures water and sediment before they"
        " reach the injection servo.",
        "FAR 23.955, Cessna DS-155",
        baseline="CDR",
        allocated="Fuel Systems",
        needs=["design", "verification_case"],
        effort=12,
        priorities={"development": 4, "safety": 9, "maintenance": 3},
    ))

    # ════════════════════════════════════════════════════════════
    # AVIONICS SUBSYSTEM
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "AVNC0000",
        "Avionics Suite — Garmin G1000 NXi",
        "<p>The avionics shall be the Garmin G1000 NXi integrated"
        " flight deck comprising a 10.4-inch PFD, 10.4-inch MFD,"
        " dual GIA 64W integrated avionics units, GDC 74A digital"
        " air data computer, GRS 79 ADAHRS, GMU 44 magnetometer,"
        " and GEA 71B engine/airframe unit.</p>",
        "functional", "approved", "critical",
        "The G1000 NXi was selected over the legacy G1000 for its"
        " faster processors, WAAS/SBAS LPV approach capability,"
        " visual approach guidance, and HSI map overlay.  This"
        " provides a training platform that familiarises student"
        " pilots with the glass-cockpit environment they will"
        " encounter in airline operations.",
        "Garmin G1000 NXi System Manual",
        baseline="CDR",
        allocated="Avionics Integration",
        needs=["design", "verification_case"],
        effort=50,
        priorities={"development": 8, "customers": 9, "safety": 6},
    ))

    r.append(_req(
        "AVNC0000", "AVNC0001",
        "Primary Flight Display (PFD)",
        "<p>A 10.4-inch diagonal, 1024×768 pixel, sunlight-readable"
        " LCD shall display: attitude indicator with flight"
        " director, indicated airspeed tape (IAS) with TAS window,"
        " barometric altimeter tape, vertical speed indicator"
        " (VSI), heading indicator with HSI, turn coordinator,"
        " and slip/skid ball.  The PFD shall revert to composite"
        " mode if the MFD fails, displaying engine strip below"
        " the flight instruments.</p>",
        "interface", "approved", "critical",
        "The PFD is the pilot's primary instrument.  Reversionary"
        " mode (composite display) ensures continued safe flight"
        " if the MFD fails — a critical redundancy feature for a"
        " single-pilot IFR platform.",
        "Garmin G1000 NXi Pilot's Guide",
        needs=["design", "verification_case"],
        effort=12,
        priorities={"development": 4, "safety": 8, "customers": 7},
    ))

    r.append(_req(
        "AVNC0000", "AVNC0002",
        "Multi-Function Display (MFD)",
        "<p>A second 10.4-inch LCD shall display: moving map"
        " with navigation data overlay, engine indication system"
        " (EIS) strip, traffic information (TIS), weather data"
        " (FIS-B), terrain awareness (TAWS-B), and flight plan"
        " management.  The MFD shall also serve as the primary"
        " interface for checklist display, system status, and"
        " auxiliary video input.</p>",
        "interface", "approved", "high",
        "The MFD is the information hub.  Moving-map navigation"
        " with own-ship position dramatically improves situational"
        " awareness versus paper charts — a key safety benefit"
        " for student pilots navigating unfamiliar airspace.",
        "Garmin G1000 NXi Pilot's Guide",
        needs=["design"],
        effort=10,
        priorities={"development": 4, "customers": 8, "safety": 5},
    ))

    # Decision record for G1000 NXi selection
    r.append(_req(
        "AVNC0000", "AVNC0010",
        "Avionics Architecture Decision",
        "<p>The Garmin G1000 NXi was selected as the integrated"
        " avionics platform.  This decision was recorded per the"
        " system engineering decision process.</p>",
        "design", "approved", "medium",
        "Decision record: G1000 NXi vs G1000 vs G500 TXi trade"
        " study concluded the NXi provides the best balance of"
        " capability (WAAS/SBAS LPV), installed cost, and"
        " familiarity for the training fleet market.",
        "Systems Engineering Decision Log",
        normative=False,
        needs=[],
        effort=0,
        priorities={},
    ))

    r.append(_req(
        "AVNC0000", "AVNC0003",
        "Navigation Systems",
        "<p>Integrated navigation shall provide: GPS/WAAS with"
        " SBAS for LPV approach capability, VOR/LOC/GS receiver,"
        " and DME (distance measuring equipment) interrogation."
        "  Navigation data shall be sourced from the GIA 64W"
        " integrated avionics units with ARINC 429 interfaces"
        " to the PFD and MFD.</p>",
        "functional", "approved", "critical",
        "WAAS/SBAS LPV approaches provide ILS-like precision"
        " without ground-based infrastructure — critical for"
        " accessing smaller airports.  VOR/LOC/GS provides"
        " redundancy and compatibility with legacy procedures.",
        "14 CFR 91.227, Garmin G1000 NXi AFMS",
        needs=["design", "verification_case"],
        effort=15,
        priorities={"development": 5, "safety": 8, "customers": 6},
    ))

    r.append(_req(
        "AVNC0003", "AVNC0004",
        "GPS/WAAS Receiver",
        "<p>The GIA 64W shall contain a 15-channel WAAS-enabled GPS"
        " receiver with SBAS augmentation providing LPV approach"
        " capability to 200 ft decision height.  RAIM (Receiver"
        " Autonomous Integrity Monitoring) shall provide integrity"
        " monitoring with fault detection and exclusion.  Position"
        " update rate shall be 5 Hz minimum.</p>",
        "functional", "approved", "critical",
        "LPV capability provides ILS-equivalent minima at thousands"
        " of US airports that lack ILS infrastructure.  RAIM is"
        " the integrity layer that makes GPS safe for sole-means"
        " navigation.",
        "TSO-C145d, Garmin GIA 64W Specification",
        needs=["design"],
        effort=8,
        priorities={"development": 4, "safety": 9},
    ))

    r.append(_req(
        "AVNC0003", "AVNC0005",
        "VOR/ILS Navigation Receiver",
        "<p>The GIA 64W shall include a VOR/LOC/GS navigation"
        " receiver with digital signal processing, automatic"
        " station identification decoding, and CDI (Course"
        " Deviation Indicator) display on both PFD and standby"
        " instrument.  GS capture shall be from above or below"
        " with automatic sensitivity scaling.</p>",
        "functional", "approved", "high",
        "While GPS is the primary navigation source, VOR/ILS"
        " provides a dissimilar-technology backup that is immune"
        " to GPS jamming/outages.  ILS capability also enables"
        " training for the instrument rating practical test.",
        "TSO-C36e, TSO-C40c",
        needs=["design"],
        effort=5,
        priorities={"development": 2, "safety": 5, "customers": 4},
    ))

    r.append(_req(
        "AVNC0000", "AVNC0006",
        "Communication Systems",
        "<p>Dual VHF COM transceivers (118.000–136.975 MHz) with"
        " 8.33 kHz channel spacing, automatic squelch, and"
        " GMA 1360 audio panel integration.  COM1 and COM2 shall"
        " be independently tunable from the PFD bezel or MFD"
        " controls, with the active and standby frequencies"
        " displayed on the PFD top bar.</p>",
        "interface", "approved", "high",
        "8.33 kHz spacing is now mandatory in European airspace"
        " above FL195 and is being extended.  Dual COM radios"
        " enable simultaneous monitoring of ATC and ATIS/AWOS.",
        "ICAO Annex 10, EASA AMC 20-25",
        needs=["design", "verification_case"],
        effort=8,
        priorities={"development": 3, "safety": 5, "customers": 6},
    ))

    r.append(_req(
        "AVNC0006", "AVNC0007",
        "VHF COM Transceivers",
        "<p>Each COM transceiver shall provide 10 W minimum carrier"
        " power (16 W PEP for AM), with a receiver sensitivity"
        " of -107 dBm for 6 dB SINAD at 1 kHz tone, 30% modulation."
        "  The audio panel shall provide pilot isolate, crew"
        " isolate, and all modes with stereo music muting during"
        " radio reception.</p>",
        "functional", "approved", "medium",
        needs=["design"],
        effort=4,
        priorities={"development": 2, "customers": 3},
    ))

    r.append(_req(
        "AVNC0006", "AVNC0008",
        "Mode S Transponder with ADS-B Out",
        "<p>A Mode S transponder (GTX 335R) shall provide ADS-B Out"
        " on 1090 MHz Extended Squitter with a minimum of 125 W"
        " transmit power, meeting DO-260B.  Position source shall"
        " be the GIA 64W GPS/WAAS receiver.  ADS-B In shall be"
        " provided via the GTX 345R for TIS-B and FIS-B reception"
        " on 978 MHz UAT.</p>",
        "functional", "approved", "critical",
        "ADS-B Out is mandated by 14 CFR 91.225 for operations"
        " in most controlled airspace after January 1, 2020."
        "  ADS-B In provides traffic (TIS-B) and weather (FIS-B)"
        " data to the MFD — a significant safety enhancement at"
        " minimal additional hardware cost.",
        "DO-260B, 14 CFR 91.225, 14 CFR 91.227",
        needs=["design", "verification_case"],
        effort=10,
        priorities={"development": 4, "safety": 9, "customers": 7},
    ))

    r.append(_req(
        "AVNC0006", "AVNC0009",
        "Audio Panel — GMA 1360",
        "<p>The GMA 1360 audio panel shall provide: 6-place stereo"
        " intercom with individual volume/squelch, marker beacon"
        " receiver (75 MHz) with three-light indicator, Bluetooth"
        " connectivity for phone/music, split COM capability"
        " (pilot on COM1, copilot on COM2), and a 3.5 mm auxiliary"
        " music input with automatic muting during radio reception.</p>",
        "interface", "approved", "medium",
        needs=["design"],
        effort=3,
        priorities={"development": 2, "customers": 6},
    ))

    # ════════════════════════════════════════════════════════════
    # FLIGHT CONTROLS SUBSYSTEM
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "FLTC0000",
        "Flight Control System",
        "<p>A conventional mechanical flight control system using"
        " push-pull tubes and stainless steel cables with"
        " turnbuckle tension adjustment, per FAR 23.671 through"
        " 23.703.  All primary control surfaces shall be mass-"
        " balanced to prevent flutter within the flight envelope.</p>",
        "functional", "approved", "critical",
        "Mechanical controls provide direct tactile feedback to"
        " the pilot — there is no lag or artificial feel system."
        "  This is essential for a training aircraft where the"
        " student must learn to interpret control forces directly.",
        "FAR 23.671, FAR 23.629 (Flutter)",
        baseline="PDR",
        allocated="Flight Controls Team",
        needs=["design", "verification_case"],
        effort=35,
        priorities={"development": 5, "safety": 10, "customers": 3},
    ))

    r.append(_req(
        "FLTC0000", "FLTC0001",
        "Primary Flight Controls",
        "<p>Dual control yokes (left and right) shall actuate"
        " ailerons via a cable-and-pulley system with ball-"
        " bearing pulleys, elevators via push-pull tubes with"
        " rod-end bearings, and rudder via stainless steel cables."
        "  All control cables shall be 7×19 stainless steel with"
        " a minimum breaking strength of 920 lb.</p>",
        "functional", "approved", "critical",
        needs=["design"],
        effort=15,
        priorities={"development": 4, "safety": 9},
    ))

    r.append(_req(
        "FLTC0001", "FLTC0002",
        "Aileron Control",
        "<p>Frise-type ailerons with differential throw (up: 20° ±1°,"
        " down: 15° ±1°) shall provide roll control at all speeds"
        " above V_S1.  The ailerons shall be mass-balanced to"
        " 100% static balance about the hinge line.  Frise nose"
        " profile shall protrude into the airstream on the up-"
        " going aileron to provide adverse-yaw compensation.</p>",
        "design", "approved", "high",
        "Differential aileron throw is the primary adverse-yaw"
        " mitigation technique on the Cessna 172.  More up-travel"
        " than down-travel increases drag on the up-going wing,"
        " offsetting the induced-drag asymmetry.  Combined with"
        " the Frise nose this produces a proverse yaw moment that"
        " reduces the need for coordinated rudder input.",
        needs=["design", "verification_case"],
        effort=8,
        priorities={"development": 3, "safety": 5},
    ))

    r.append(_req(
        "FLTC0001", "FLTC0003",
        "Elevator Control",
        "<p>The elevator shall be actuated by push-pull tubes from"
        " the control yoke through a bellcrank to the elevator"
        " horn.  Up travel shall be 25° ±2°, down travel 15° ±2°."
        "  An anti-servo trim tab on the right elevator shall"
        " provide pitch trim forces of ±30 lb at the yoke across"
        " the CG range at all speeds.</p>",
        "design", "approved", "high",
        "Push-pull tubes provide precise elevator control without"
        " cable stretch or temperature effects.  The anti-servo"
        " tab moves in the same direction as the elevator,"
        " providing a linear trim-force gradient that pilots"
        " find intuitive.",
        needs=["design"],
        effort=6,
        priorities={"development": 3, "safety": 5},
    ))

    r.append(_req(
        "FLTC0001", "FLTC0004",
        "Rudder Control",
        "<p>Cable-actuated rudder with adjustable pedal positions"
        " (3 positions by pin selection).  Rudder travel shall be"
        " ±24° ±2°.  A ground-adjustable trim tab shall provide"
        " cruise rudder trim for hands-off coordinated flight"
        " at typical cruise power settings (2400 RPM, leaned).</p>",
        "design", "approved", "medium",
        needs=["design"],
        effort=4,
        priorities={"development": 2, "safety": 3, "customers": 4},
    ))

    r.append(_req(
        "FLTC0000", "FLTC0005",
        "Secondary Flight Controls — Flaps",
        "<p>Single-slotted Fowler flaps, electrically actuated by"
        " a 28V DC motor driving a jackscrew mechanism, shall"
        " provide four pre-set positions: 0° (UP), 10°, 20°, and"
        " 30° (FULL).  Transit time shall be 6 ±1 seconds end-to-"
        " end.  A mechanical flap position indicator on the left"
        " wing root and an electrical position sensor feeding the"
        " PFD shall display current flap setting.</p>",
        "functional", "approved", "high",
        "Fowler flaps increase both camber and wing area, providing"
        " a high C_Lmax for short-field landing.  The 30° setting"
        " is primarily a drag device for steep approaches; 20° is"
        " the normal landing setting.  The Cessna 172S POH"
        " recommends 10° for short-field takeoff.",
        needs=["design", "verification_case"],
        effort=10,
        priorities={"development": 4, "safety": 6, "customers": 5},
    ))

    r.append(_req(
        "FLTC0005", "FLTC0006",
        "Flap Actuation & Indication",
        "<p>A 28V DC permanent-magnet motor with a 40:1 worm gear"
        " reduction shall drive a jackscrew mechanism connected"
        " to the flap torque tube.  Limit switches at each detent"
        " position shall cut motor power.  A flap position"
        " potentiometer shall provide analog position feedback"
        " to the GEA 71B for PFD indication.  Motor current shall"
        " be limited to 5 A by a panel-mounted circuit breaker.</p>",
        "design", "approved", "high",
        "Electric flaps reduce pilot workload versus manual (Johnson"
        " bar) flaps, freeing the right hand for throttle and"
        " mixture adjustment during the approach.  The detent"
        " positions eliminate the need for the pilot to judge"
        " intermediate settings.",
        allocated="Electrical Integration",
        needs=["design"],
        effort=5,
        priorities={"development": 2, "safety": 4},
    ))

    r.append(_req(
        "FLTC0000", "FLTC0007",
        "Pitch Trim System",
        "<p>A manual pitch trim wheel located on the centre console,"
        " driving the elevator trim tab via a cable-and-drum"
        " mechanism, shall provide ±30 lb of stick force relief"
        " across the speed range.  An electric pitch trim switch"
        " on the pilot's yoke (split switch requiring simultaneous"
        " depression of both halves) shall provide servo-driven"
        " trim for fine adjustment in cruise.  Trim position shall"
        " be indicated by a mechanical pointer on the console and"
        " on the PFD.</p>",
        "design", "approved", "medium",
        "The split trim switch (both halves must be pressed together)"
        " prevents inadvertent activation from accidental contact."
        "  Electric trim reduces pilot fatigue on longer flights"
        " but the manual wheel provides a reliable mechanical"
        " baseline and is used as the primary means of trimming.",
        needs=["design"],
        effort=4,
        priorities={"development": 2, "customers": 5},
    ))

    # ── Landing Gear ───────────────────────────────────────────────────────

    r.append(_req(
        "ACFT0000", "LNDG0000",
        "Landing Gear System",
        "<p>Tricycle fixed landing gear configuration with a"
        " steerable nosewheel, tubular spring steel main gear"
        " legs, and Cleveland hydraulic disc brakes on the main"
        " wheels.  The gear shall absorb landing loads per"
        " FAR 23.471 through 23.511 with a design sink rate of"
        " 10 fps at maximum landing weight of 2550 lb.</p>",
        "design", "approved", "critical",
        "Fixed gear is chosen for simplicity, lower weight, and"
        " elimination of the retraction mechanism failure modes."
        "  Spring steel legs provide excellent energy absorption"
        " and are virtually maintenance-free compared to oleo"
        " struts.",
        baseline="CDR",
        allocated="Landing Gear Team",
        needs=["design", "verification_case"],
        effort=20,
        priorities={"development": 3, "safety": 6, "maintenance": 5},
    ))

    r.append(_req(
        "LNDG0000", "LNDG0001",
        "Main Gear Legs & Wheels",
        "<p>Tubular spring steel (6150 chrome-vanadium) main gear"
        " legs, heat-treated to 44-48 HRC, shall attach to the"
        " fuselage at forged aluminium bulkhead fittings.  Wheels"
        " shall be Cleveland 40-77B 6.00-6 with 6-ply tyres rated"
        " to 100 mph.  The track shall be 8 ft 4.5 in.</p>",
        "design", "approved", "high",
        needs=["design"],
        effort=6,
        priorities={"development": 2, "safety": 4},
    ))

    r.append(_req(
        "LNDG0000", "LNDG0002",
        "Steerable Nose Gear",
        "<p>A steerable nose gear with a 5.00-5 tyre shall provide"
        " ±12° steering authority via push-pull rods connected"
        " to the rudder pedals.  A shimmy damper (hydraulic"
        " piston type) shall prevent nosewheel oscillation up to"
        " 40 knots ground speed.  A bungee centering system shall"
        " return the nosewheel to centre when unloaded.</p>",
        "design", "approved", "high",
        "The steerable nosewheel tied to rudder pedals gives the"
        " pilot intuitive ground steering — the same foot motion"
        " used for yaw control in flight.  The shimmy damper is"
        " a wear item requiring inspection every 100 hours; its"
        " design as a sealed hydraulic unit minimizes maintenance.",
        needs=["design"],
        effort=5,
        priorities={"development": 2, "safety": 4, "maintenance": 4},
    ))

    r.append(_req(
        "LNDG0000", "LNDG0003",
        "Hydraulic Braking System",
        "<p>Cleveland 30-52 toe brakes on the pilot's rudder pedals,"
        " and 30-52N on the co-pilot's pedals, shall actuate"
        " single-disc calipers on each main wheel via a closed"
        " hydraulic system using MIL-PRF-5606 hydraulic fluid."
        "  The parking brake shall be a pull-knob on the instrument"
        " panel that locks hydraulic pressure in the brake lines."
        "  The system shall hold the aircraft stationary at 1800"
        " RPM (full static run-up).</p>",
        "functional", "approved", "critical",
        "Toe brakes provide intuitive differential braking for"
        " tight turning on the ground.  The parking brake allows"
        " hands-free run-up.  Adequate holding force at full"
        " static RPM is essential for the pre-takeoff engine check.",
        needs=["design", "verification_case"],
        effort=6,
        priorities={"development": 2, "safety": 8},
    ))

    # ════════════════════════════════════════════════════════════
    # ELECTRICAL SUBSYSTEM
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "ELEC0000",
        "Electrical Power System",
        "<p>A 28V DC single-wire, negative-ground electrical system"
        " shall provide power to all aircraft systems per FAR"
        " 23.1351 through 23.1365.  Normal power source shall be"
        " a 60-amp engine-driven alternator.  Emergency power"
        " shall be provided by a 24V sealed lead-acid battery"
        " rated for 30 minutes of essential bus operation.</p>",
        "functional", "approved", "critical",
        "28V was selected over 14V to reduce current (and therefore"
        " wire gauge and weight) for the same power delivery."
        "  This matters with the G1000's ~12A continuous draw."
        "  The essential bus concept ensures critical systems"
        " (PFD, COM1, GPS, transponder) remain powered after an"
        " alternator failure.",
        "FAR 23.1351, FAR 23.1353",
        baseline="CDR",
        allocated="Electrical Systems",
        needs=["design", "verification_case"],
        effort=25,
        priorities={"development": 4, "safety": 7, "maintenance": 3},
    ))

    r.append(_req(
        "ELEC0000", "ELEC0001",
        "Alternator & Regulation",
        "<p>A 60-amp, 28V, engine-driven alternator (belt-driven at"
        " 1.5× engine speed) with integral solid-state voltage"
        " regulator shall provide a nominal output of 28.25 ±"
        " 0.25 V.  The alternator shall maintain bus voltage above"
        " 26V at all engine speeds above 1200 RPM with full"
        " electrical load, and shall provide a minimum of 10 A"
        " of charging current to the battery at 1000 RPM.</p>",
        "design", "approved", "high",
        needs=["design"],
        effort=5,
        priorities={"development": 3, "safety": 4},
    ))

    r.append(_req(
        "ELEC0000", "ELEC0002",
        "Battery — Emergency Power",
        "<p>A 24V, 13.6 Ah sealed lead-acid (SLA) battery, located"
        " in the engine compartment on the firewall, shall provide:"
        " (a) engine starting current of 200 A peak, (b) emergency"
        " power to the essential bus for 30 minutes minimum at"
        " 15 A load after alternator failure, (c) voltage"
        " stabilisation (acting as a large capacitor) during"
        " normal alternator operation.  The battery shall be a"
        " Gill G-243 or Concorde RG-243 sealed unit requiring"
        " no electrolyte maintenance.</p>",
        "design", "approved", "critical",
        "SLA batteries eliminate acid spill risk and maintenance"
        " requirements.  30 minutes of essential bus power at a"
        " 15 A load provides sufficient endurance to reach an"
        " airport in an alternator-out scenario in the traffic"
        " pattern (worst case).",
        needs=["verification_case"],
        effort=5,
        priorities={"development": 2, "safety": 8},
    ))

    r.append(_req(
        "ELEC0000", "ELEC0003",
        "Power Distribution & Bus Architecture",
        "<p>The electrical system shall use a split-bus architecture:"
        " a Main Bus powering non-essential loads (cabin lighting,"
        " auxiliary power receptacle, second COM radio) and an"
        " Essential Bus powering flight-critical loads (PFD,"
        " COM1, GPS/NAV, transponder, pitot heat, electric trim)."
        "  A bus-tie relay shall connect the buses during normal"
        " operation and isolate the Essential Bus during emergency."
        "  All circuits shall be protected by pull-type circuit"
        " breakers rated at 125% of maximum continuous load.</p>",
        "design", "approved", "high",
        needs=["design"],
        effort=8,
        priorities={"development": 3, "safety": 6},
    ))

    r.append(_req(
        "ELEC0000", "ELEC0004",
        "External Power Receptacle",
        "<p>A 3-pin MS3506-compatible external power receptacle,"
        " located on the left side of the cowling, shall accept"
        " 28V DC Ground Power Unit (GPU) input for engine starting"
        " and ground maintenance operations.  A relay shall isolate"
        " the aircraft bus from the GPU if reverse polarity is"
        " detected.</p>",
        "interface", "approved", "low",
        needs=["design"],
        effort=2,
        priorities={"development": 1, "maintenance": 3},
    ))

    # ════════════════════════════════════════════════════════════
    # ENVIRONMENTAL CONTROL SUBSYSTEM
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "ENVR0000",
        "Environmental Control System",
        "<p>The cabin environmental system shall provide heating,"
        " ventilation, and windshield defrost per FAR 23.831."
        "  The system shall maintain a cabin temperature between"
        " 10-30°C across the operating altitude range with"
        " outside air temperatures (OAT) from -20°C to +40°C.</p>",
        "functional", "approved", "high",
        baseline="CDR",
        needs=["design"],
        effort=10,
        priorities={"development": 2, "customers": 7, "safety": 2},
    ))

    r.append(_req(
        "ENVR0000", "ENVR0001",
        "Cabin Heat — Exhaust Heat Exchanger",
        "<p>Engine exhaust gases shall flow through a muff-type"
        " stainless steel heat exchanger (shroud).  A cabin heat"
        " control cable shall regulate a butterfly valve that"
        " mixes heated ram air with ambient air to achieve"
        " the desired cabin temperature.  A CO detector shall"
        " trigger a cockpit warning if CO concentration exceeds"
        " 50 ppm, indicating possible heat exchanger cracks.</p>",
        "functional", "approved", "high",
        "Exhaust-muff heating is simple, lightweight, and uses"
        " otherwise wasted thermal energy.  The CO detector is a"
        " critical safety device: muff cracks can introduce"
        " exhaust into the cabin — a recognised Cessna 172 AD"
        " item (AD 73-08-03).  The current CO detector meets"
        " the FAA's 2023 policy encouraging active CO detection.",
        "FAR 23.831, AD 73-08-03",
        needs=["design", "verification_case"],
        effort=6,
        priorities={"development": 2, "safety": 7, "customers": 5},
    ))

    r.append(_req(
        "ENVR0000", "ENVR0002",
        "Fresh Air Ventilation",
        "<p>Two adjustable fresh-air vents (eyeball-type), one each"
        " above the pilot and co-pilot stations, shall provide"
        " ram-air ventilation.  A third vent in the rear cabin"
        " ceiling shall serve rear passengers.  Each vent shall"
        " provide 3-15 CFM of fresh air, adjustable by rotating"
        " the vent bezel.</p>",
        "functional", "approved", "medium",
        needs=["design"],
        effort=3,
        priorities={"development": 1, "customers": 5},
    ))

    r.append(_req(
        "ENVR0000", "ENVR0003",
        "Windshield Defrost",
        "<p>A defroster plenum connected to the cabin heat system"
        " shall direct heated air onto the inner surface of the"
        " windshield via a multi-slot diffuser.  The defroster"
        " shall raise windshield surface temperature at least"
        " 15°C above OAT within 2 minutes of activation.</p>",
        "functional", "approved", "critical",
        "Windshield fogging/icing can completely obscure the"
        " pilot's forward view, making this a safety-critical"
        " system for IFR operations or any flight encountering"
        " visible moisture.",
        needs=["design", "verification_case"],
        effort=4,
        priorities={"development": 1, "safety": 9},
    ))

    # ════════════════════════════════════════════════════════════
    # SAFETY SYSTEMS
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "SAFE0000",
        "Safety Systems",
        "<p>All safety systems shall meet FAR Part 23 requirements"
        " for occupant protection, hazard warning, and emergency"
        " equipment.  The safety architecture shall follow the"
        " defence-in-depth principle: no single failure shall"
        " result in a hazardous or catastrophic condition.</p>",
        "functional", "approved", "critical",
        "Safety is the overriding design imperative for a training"
        " aircraft.  The Cessna 172 has the best safety record of"
        " any general aviation aircraft (0.56 fatal accidents per"
        " 100,000 flight hours) — this must be preserved and"
        " enhanced.",
        "FAR 23.1300, FAR 23.1309",
        needs=["design", "verification_case"],
        effort=20,
        priorities={"development": 3, "safety": 10, "customers": 5},
    ))

    r.append(_req(
        "SAFE0000", "SAFE0001",
        "Stall Warning System",
        "<p>A pneumatic stall warning horn, driven by a suction-"
        " operated reed mounted in the left wing leading edge,"
        " shall activate between 5 and 10 knots above the stall"
        " speed in all configurations (flaps up, 10°, 20°, 30°)."
        "  The horn shall produce a sound pressure level of at"
        " least 85 dB(A) at the pilot's ear position.  The system"
        " shall be operable with the master switch off (no"
        " electrical power required).</p>",
        "functional", "approved", "critical",
        "A purely pneumatic stall warning (no electronics) ensures"
        " operation even with total electrical failure.  The 5-10"
        " knot margin provides adequate warning without nuisance"
        " activation during normal approach speeds.",
        "FAR 23.207",
        needs=["design", "verification_case"],
        effort=5,
        priorities={"development": 2, "safety": 10},
    ))

    r.append(_req(
        "SAFE0000", "SAFE0002",
        "Engine Fire Detection",
        "<p>A thermocouple-based fire detection system in the engine"
        " compartment shall trigger a red FIRE warning light on"
        " the instrument panel if compartment temperature exceeds"
        " 600°F (316°C).  The system shall be self-testing:"
        " pressing the TEST button shall illuminate the warning"
        " light and verify circuit continuity.</p>",
        "functional", "approved", "critical",
        "Engine compartment fire is a time-critical emergency."
        "  Early detection enables the pilot to execute the"
        " emergency procedure (fuel shutoff, dive to extinguish,"
        " forced landing) before structural damage occurs.",
        needs=["design", "verification_case"],
        effort=4,
        priorities={"development": 1, "safety": 10},
    ))

    r.append(_req(
        "SAFE0000", "SAFE0003",
        "Emergency Locator Transmitter (ELT)",
        "<p>The Artex ME406 ELT or equivalent shall transmit on"
        " 406.028 MHz (primary, to COSPAS-SARSAT satellites)"
        " and 121.5 MHz (homing beacon), meeting TSO-C126b."
        "  The ELT shall activate automatically upon detecting"
        " a 4.5 ft/s (2.3g) deceleration along its longitudinal"
        " axis.  The remote switch on the instrument panel shall"
        " allow manual activation and test (ARM/ON/TEST).</p>",
        "functional", "approved", "critical",
        "406 MHz ELTs provide global coverage via the COSPAS-SARSAT"
        " satellite constellation with a position accuracy of"
        " 1-3 km (vs 15-20 km for legacy 121.5 MHz).  Automatic"
        " G-switch activation ensures the ELT works even if the"
        " crew is incapacitated.",
        "TSO-C126b",
        needs=["verification_case"],
        effort=3,
        priorities={"development": 1, "safety": 10},
    ))

    r.append(_req(
        "SAFE0000", "SAFE0004",
        "Exterior Lighting",
        "<p>Navigation lights (red/green wingtip, white tail) shall"
        " meet FAR 23.1385 (110° horizontal coverage, +/– 5°"
        " vertical).  Anti-collision lights (red rotating beacon"
        " on the fin tip, white strobes on each wingtip) shall"
        " meet FAR 23.1401 with 360° horizontal coverage and"
        " 400 effective candela minimum.  A landing/taxi light"
        " (250 W halogen or LED equivalent, 100,000 cd) shall be"
        " mounted in the left wing leading edge and controlled by"
        " a three-position switch (OFF/TAXI/LAND).</p>",
        "functional", "approved", "high",
        "The move from halogen to LED lighting reduces electrical"
        " load by ~70% while increasing lamp life from ~25 to"
        " ~10,000+ hours.  This is an allowed owner-performed"
        " preventive maintenance item (FAR 43 Appendix A).",
        "FAR 23.1385, FAR 23.1401",
        needs=["design"],
        effort=4,
        priorities={"development": 2, "customers": 3, "safety": 6},
    ))

    # ════════════════════════════════════════════════════════════
    # DERIVED REQUIREMENTS (no parent — external source)
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        None, "AD2024001",
        "Airworthiness Directive — CO Detector Retrofit",
        "<p>All Cessna 172S aircraft manufactured before 2025 shall"
        " be retrofitted with an active carbon monoxide (CO)"
        " detector per FAA AD 2024-01-05.  The detector shall"
        " provide a visual and aural alert at 50 ppm CO and"
        " shall be connected to aircraft power with a battery"
        " backup.  Compliance shall be completed within 12"
        " calendar months of the AD effective date.</p>",
        "constraint", "approved", "critical",
        "This AD was prompted by NTSB Safety Recommendation A-22-3"
        " following multiple CO-related incidents in general"
        " aviation.  Mandatory compliance is required for"
        " continued airworthiness.",
        "FAA AD 2024-01-05, NTSB A-22-3",
        derived=True,
        needs=["design"],
        effort=8,
        priorities={"safety": 10, "maintenance": 5},
    ))

    # ════════════════════════════════════════════════════════════
    # NON-NORMATIVE HEADING (for publish output)
    # ════════════════════════════════════════════════════════════

    r.append(_req(
        "ACFT0000", "OVERVIEW",
        "— System Architecture Overview —",
        "<p>This section provides an overview of the Cessna 172S"
        " system architecture and describes the relationships"
        " between the major aircraft subsystems.  The requirements"
        " that follow in this document are normative.</p>",
        "design", "approved", "low",
        normative=False,
        needs=[],
        effort=0,
        priorities={},
    ))

    return r


# ── verification cases ────────────────────────────────────────────────────────

VERIFICATION_CASES = [
    {"id": "VCAF0001", "name": "Structural Static Test", "method": "test",
     "description": "Static load test of airframe to ultimate load per FAR 23.305"},
    {"id": "VCAF0002", "name": "Crashworthiness Analysis", "method": "analysis",
     "description": "FAR 23.561 emergency landing dynamic FEA analysis"},
    {"id": "VCPR0001", "name": "Engine Run-Up Test", "method": "test",
     "description": "Full-power engine run at 2700 RPM, magneto drop check, fuel flow verification"},
    {"id": "VCPR0002", "name": "Fuel System Flow Test", "method": "test",
     "description": "Fuel flow test at all flight attitudes and power settings per FAR 23.955"},
    {"id": "VCAV0001", "name": "Avionics Integration Test", "method": "test",
     "description": "End-to-end G1000 NXi integration test: PFD/MFD/ADAHRS/GPS/COM"},
    {"id": "VCAV0002", "name": "ADS-B Compliance Test", "method": "test",
     "description": "ADS-B Out performance verification per 14 CFR 91.227, DO-260B"},
    {"id": "VCFC0001", "name": "Flight Control Free-Play Check", "method": "inspection",
     "description": "All control surfaces: free play < 0.125 inch, full travel verified"},
    {"id": "VCFC0002", "name": "Flutter Analysis", "method": "analysis",
     "description": "Flutter analysis per FAR 23.629: all surfaces mass-balanced, damping verified"},
    {"id": "VCEL0001", "name": "Electrical Load Analysis", "method": "analysis",
     "description": "Electrical load analysis showing bus voltage ≥ 26V under all flight conditions"},
    {"id": "VCEL0002", "name": "Battery Endurance Test", "method": "test",
     "description": "Essential bus endurance test: 30 minutes at 15 A load from full charge"},
    {"id": "VCFL0001", "name": "Fuel Flow Test", "method": "test",
     "description": "Fuel flow ≥ 14 GPH at max power, selector valve all positions"},
    {"id": "VCSF0001", "name": "Stall Warning Calibration", "method": "test",
     "description": "Stall warning horn activation verified 5-10 kn above stall in all configs"},
    {"id": "VCSF0002", "name": "ELT Functional Test", "method": "test",
     "description": "406 MHz ELT activation test per TSO-C126b, G-switch threshold verified"},
    {"id": "VCCB0001", "name": "Brake Holding Test", "method": "test",
     "description": "Parking brake holding force verified at full static run-up (1800 RPM)"},
    {"id": "VCEV0001", "name": "CO Detector Validation", "method": "test",
     "description": "CO detector activation at 50 ±10 ppm, aural/visual alert verified"},
]

VC_LINKS: dict[str, list[str]] = {
    "VCAF0001": ["AFRM0000", "AFRM0005"],
    "VCAF0002": ["AFRM0002"],
    "VCPR0001": ["PROP0001", "PROP0003"],
    "VCPR0002": ["PROP0006"],
    "VCAV0001": ["AVNC0000", "AVNC0001"],
    "VCAV0002": ["AVNC0008"],
    "VCFC0001": ["FLTC0000", "FLTC0001", "FLTC0002"],
    "VCFC0002": ["FLTC0000", "FLTC0002"],
    "VCEL0001": ["ELEC0000", "ELEC0001"],
    "VCEL0002": ["ELEC0002"],
    "VCFL0001": ["PROP0006", "AFRM0006"],
    "VCSF0001": ["SAFE0001"],
    "VCSF0002": ["SAFE0003"],
    "VCCB0001": ["LNDG0003"],
    "VCEV0001": ["ENVR0001", "AD2024001"],
}

# ── relations (source, target, relation_type) ─────────────────────────────────

RELATIONS = [
    # Wing structure chain
    ("AFRM0005", "AFRM0004", "refines"),
    ("AFRM0006", "AFRM0004", "refines"),
    ("AFRM0008", "AFRM0007", "refines"),
    ("AFRM0009", "AFRM0007", "refines"),

    # Engine subsystem chain
    ("PROP0002", "PROP0001", "refines"),
    ("PROP0003", "PROP0001", "refines"),
    ("PROP0004", "PROP0001", "refines"),
    ("PROP0006", "PROP0000", "refines"),

    # Avionics subsystem chain
    ("AVNC0001", "AVNC0000", "refines"),
    ("AVNC0002", "AVNC0000", "refines"),
    ("AVNC0004", "AVNC0003", "refines"),
    ("AVNC0005", "AVNC0003", "refines"),
    ("AVNC0007", "AVNC0006", "refines"),
    ("AVNC0008", "AVNC0006", "refines"),
    ("AVNC0009", "AVNC0006", "refines"),

    # Flight controls chain
    ("FLTC0002", "FLTC0001", "refines"),
    ("FLTC0003", "FLTC0001", "refines"),
    ("FLTC0004", "FLTC0001", "refines"),
    ("FLTC0006", "FLTC0005", "refines"),
    ("FLTC0007", "FLTC0000", "refines"),

    # Landing gear chain
    ("LNDG0001", "LNDG0000", "refines"),
    ("LNDG0002", "LNDG0000", "refines"),

    # Electrical chain
    ("ELEC0001", "ELEC0000", "refines"),
    ("ELEC0002", "ELEC0000", "refines"),
    ("ELEC0003", "ELEC0000", "refines"),
    ("ELEC0004", "ELEC0000", "refines"),

    # Environmental chain
    ("ENVR0001", "ENVR0000", "refines"),
    ("ENVR0002", "ENVR0000", "refines"),
    ("ENVR0003", "ENVR0000", "refines"),

    # Safety chain
    ("SAFE0001", "SAFE0000", "refines"),
    ("SAFE0002", "SAFE0000", "refines"),
    ("SAFE0003", "SAFE0000", "refines"),
    ("SAFE0004", "SAFE0000", "refines"),

    # Cross-system dependencies (key integrations)
    ("AVNC0000", "ELEC0000", "depends"),        # Avionics needs electrical power
    ("FLTC0005", "ELEC0000", "depends"),         # Flaps electrically actuated
    ("PROP0006", "ELEC0000", "satisfies"),       # Electric boost pump requires power
    ("ENVR0001", "PROP0001", "depends"),         # Cabin heat from engine exhaust
    ("SAFE0000", "AFRM0000", "derives"),         # Safety derives constraints from airframe
    ("LNDG0003", "ELEC0000", "depends"),         # Brake system needs no electrical — but indicator does
    ("AD2024001", "ENVR0001", "satisfies"),      # CO detector AD satisfied by cabin heat CO sensor
    ("AVNC0008", "AVNC0004", "depends"),         # ADS-B needs GPS position source
    ("ELEC0002", "ELEC0000", "depends"),         # Battery sizing depends on electrical bus loads
    ("AVNC0000", "FLTC0000", "satisfies"),       # G1000 provides flight control feedback (trim, flaps)
    ("SAFE0004", "ELEC0000", "depends"),         # Lighting needs electrical power

    # Cycle demonstration (intentional: used to exercise cycle detection)
    # No cycles are intentional — the graph is a DAG.
]

# ── traces ────────────────────────────────────────────────────────────────────

TRACES = [
    {"source": "ACFT0000", "target": target, "type": "refines"}
    for target in ("AFRM0000", "PROP0000", "AVNC0000", "FLTC0000",
                   "LNDG0000", "ELEC0000", "ENVR0000", "SAFE0000")
]

# ── change requests ───────────────────────────────────────────────────────────

CHANGE_REQUESTS = [
    {"id": "CR000001", "title": "Evaluate Lycoming IO-390 Upgrade",
     "description": "Evaluate replacing IO-360-L2A (180 BHP) with IO-390-A3A6 (210 BHP)."
                    "  Net increase of 30 BHP with minimal weight gain (12 lb).  Would improve"
                    " takeoff roll and climb rate.  Requires new type certificate amendment.",
     "affected_requirements": ["PROP0001", "PROP0000", "PROP0005"],
     "status": "submitted", "submitted_by": "Powerplant Lead"},
    {"id": "CR000002", "title": "Landing Gear Corrosion Inspection",
     "description": "Add 100-hour corrosion inspection interval for spring steel main gear"
                    " legs, particularly at the forged attachment fitting interface where"
                    " paint wear can expose bare metal.",
     "affected_requirements": ["LNDG0001"],
     "status": "in_review", "submitted_by": "Maintenance Engineering"},
    {"id": "CR000003", "title": "LED Exterior Lighting Retrofit",
     "description": "Authorise LED replacement for all exterior lights as an owner-performed"
                    " preventive maintenance item.  LED bulbs reduce electrical load from 12 A"
                    " to 3.5 A, extending alternator and battery life.",
     "affected_requirements": ["SAFE0004", "ELEC0000"],
     "status": "submitted", "submitted_by": "Electrical Systems"},
    {"id": "CR000004", "title": "USB-C Charging Ports",
     "description": "Install dual USB-C (60W PD) charging ports in the cockpit for pilot"
                    " and co-pilot electronic flight bags (EFBs).  Requires circuit breaker"
                    " addition to the main bus and a supplemental type certificate (STC).",
     "affected_requirements": ["ELEC0003", "AFRM0003"],
     "status": "submitted", "submitted_by": "Avionics Integration"},
]

# ── risks ─────────────────────────────────────────────────────────────────────

RISKS = [
    {"id": "RSK00001", "title": "Engine Failure on Takeoff",
     "description": "Loss of engine power during takeoff below 500 ft AGL.  Consequences:"
                    " forced landing straight ahead or within 30° of heading.  Cessna 172's"
                    " low stall speed (48 KIAS clean) and benign stall characteristics"
                    " make survivable outcomes highly probable if the pilot maintains"
                    " airspeed.",
     "severity": "critical", "probability": "low",
     "status": "open", "mitigation": "Pre-takeoff run-up check; engine trend monitoring"},
    {"id": "RSK00002", "title": "Fuel Exhaustion in Flight",
     "description": "Fuel mismanagement or undetected leak leading to fuel exhaustion"
                    " before destination.  Leading cause of general aviation accidents"
                    " (approximately 8% of all GA accidents per AOPA Nall Report).",
     "severity": "high", "probability": "medium",
     "status": "open", "mitigation": "Fuel totalizer on G1000 MFD; pre-flight dipstick check"},
    {"id": "RSK00003", "title": "G1000 Display Overheat",
     "description": "PFD or MFD display failure due to excessive cockpit temperatures"
                    " (direct sunlight on ramp, >50°C / 122°F).  The G1000 operating"
                    " temperature specification is −20°C to +55°C.",
     "severity": "medium", "probability": "low",
     "status": "open", "mitigation": "Sunshades; cabin ventilation; reversionary mode"},
    {"id": "RSK00004", "title": "Carbon Monoxide Incapacitation",
     "description": "CO leaking into cabin via exhaust muff cracks, causing progressive"
                    " crew incapacitation (headache → confusion → unconsciousness)."
                    "  CO binds to haemoglobin with 200× the affinity of oxygen.",
     "severity": "critical", "probability": "low",
     "status": "open", "mitigation": "Active CO detector per AD 2024-01-05; muff inspection"},
    {"id": "RSK00005", "title": "Alternator Failure in IMC",
     "description": "Alternator failure while in instrument meteorological conditions (IMC)."
                    "  The essential bus provides 30 min of power — sufficient for an"
                    " approach at a nearby airport but requiring prompt action.",
     "severity": "high", "probability": "low",
     "status": "open", "mitigation": "Essential bus isolation; battery endurance ≥ 30 min"},
    {"id": "RSK00006", "title": "Icing Encounter",
     "description": "Inadvertent encounter with structural icing conditions (visible"
                    " moisture + OAT below freezing).  The Cessna 172S is NOT certified"
                    " for flight into known icing (FIKI).  Ice accumulation on wings"
                    " and tail can increase stall speed by 15-30% and reduce control"
                    " effectiveness.",
     "severity": "high", "probability": "medium",
     "status": "open", "mitigation": "Pitot heat; immediate 180° turn or descent"},
]

# ── comments ──────────────────────────────────────────────────────────────────

COMMENTS = [
    {"id": "gen-001", "author": "Chief Systems Engineer",
     "requirement_id": "ACFT0000",
     "text": "All FAR Part 23 Amendment 64 references verified against current eCFR text."
            "  Amendment 65 (effective 2025) adds active CO detector mandate — see AD2024001.",
     "resolved": False},
    {"id": "gen-002", "author": "Avionics Lead",
     "requirement_id": "AVNC0000",
     "text": "G1000 NXi software baseline is v0582.05.  Confirm with Garmin that this"
            " includes the WAAS/SBAS LPV unlock.  Supplier lead time: 16 weeks.",
     "resolved": False},
    {"id": "gen-003", "author": "Structures Engineer",
     "requirement_id": "AFRM0005",
     "text": "Main spar ultimate load FEA complete.  Positive margin of 12% at +3.8g."
            "  Recommend physical load test to validate FEA boundary conditions.",
     "resolved": True},
    {"id": "gen-004", "author": "Electrical Systems",
     "requirement_id": "ELEC0002",
     "text": "Battery endurance test at −20°C showed 28 min to essential bus dropout"
            " (vs 30 min spec).  Cold-soak effect reduces SLA capacity by ~15%."
            "  Consider upgrading to 18 Ah battery for cold-weather margin.",
     "resolved": False},
    {"id": "gen-005", "author": "Test Pilot",
     "requirement_id": "FLTC0002",
     "text": "Aileron roll rate at Va measured at 42°/s (clean).  This is within the"
            " acceptable range for a training aircraft (40-60°/s).  No adverse yaw"
            " noted during flight test — Frise/differential combination is effective.",
     "resolved": False},
    {"id": "gen-006", "author": "Flight Test",
     "requirement_id": "SAFE0001",
     "text": "Stall warning horn calibration verified in flight.  Clean stall: V_S1 = 48 KCAS,"
            " horn at 55 KCAS (7 kn margin).  Full flap: V_S0 = 40 KCAS, horn at 47 KCAS"
            " (7 kn margin).  Both within the 5-10 kn specification.",
     "resolved": False},
]

# ── decision records ──────────────────────────────────────────────────────────

DECISIONS = [
    {"id": "DEC0001", "title": "Avionics Platform Selection",
     "context": "The aircraft requires an IFR-capable integrated avionics suite suitable"
               " for both primary training and instrument rating training.",
     "decision": "Selected the Garmin G1000 NXi over the G1000 (legacy) and G500 TXi."
                "  The NXi provides WAAS/SBAS LPV approach capability, which the legacy"
                " G1000 does not support, at a marginal cost increase (~$5K per unit)."
                "  The G500 TXi has a smaller display and lacks the dual-screen redundancy"
                " of the G1000 suite.",
     "rationale": "The NXi is the current production Garmin platform with the longest"
                 " expected support lifecycle.  WAAS/LPV is essential for the training"
                 " market as more flight schools adopt LPV procedures.",
     "linked_requirements": ["AVNC0000", "AVNC0001"],
     "status": "accepted", "decided_by": "Chief Engineer"},
    {"id": "DEC0002", "title": "Engine Selection",
     "context": "The IO-360-L2A (180 BHP) was compared against the IO-390-A3A6 (210 BHP)"
               " and the O-360-A4M (carbureted, 180 BHP).",
     "decision": "Retain the IO-360-L2A.  The IO-390 adds 30 BHP but at 12 lb weight"
                " penalty, $12K cost increase, and the need for a new type certificate"
                " amendment.  The O-360 (carbureted) was rejected due to carburetor"
                " icing risk — the IO-360's fuel injection eliminates this hazard.",
     "rationale": "The 180 BHP rating is well-matched to the 172 airframe.  210 BHP"
                 " would improve climb but degrade useful load.  The fuel injection"
                 " benefit (no carb ice) is a significant safety differentiator.",
     "linked_requirements": ["PROP0000", "PROP0001", "PROP0002"],
     "status": "accepted", "decided_by": "Powerplant Lead"},
    {"id": "DEC0003", "title": "Lighting Technology — LED vs Halogen",
     "context": "Exterior lighting (nav, strobe, landing/taxi) currently halogen."
               "  LED retrofit offers reduced electrical load and longer life.",
     "decision": "Authorise LED replacements as owner-performed preventive maintenance"
                " per FAR 43 Appendix A(c)(11).  No STC required for direct-replacement"
                " LED bulbs that meet the same photometric specifications as the original"
                " halogen units.",
     "rationale": "LEDs reduce electrical load by ~70% (from 12.0 A to 3.5 A for all"
                 " exterior lights) and eliminate the 25-hour bulb replacement interval"
                 " for halogen landing lights.  This is a net safety improvement.",
     "linked_requirements": ["SAFE0004", "ELEC0000"],
     "status": "accepted", "decided_by": "Electrical Systems"},
]


# ── seed function ─────────────────────────────────────────────────────────────

def seed_demo_project(data_root: Path, force: bool = False) -> bool:
    project_root = Path(data_root) / PROJECT_ID
    if project_root.exists():
        if not force:
            return False
        shutil.rmtree(project_root)

    store = YamlStore(project_root)
    store.ensure_dirs()

    # Write _meta.yaml with workflow and quality config to demonstrate customisation
    store.write_meta({
        "name": PROJECT_NAME,
        "created": "",
        "workflow": {
            "states": ["proposed", "in_review", "approved", "implemented",
                       "verified", "rejected", "deprecated"],
            "transitions": {
                "proposed": ["in_review", "approved", "rejected"],
                "in_review": ["approved", "proposed", "rejected"],
                "approved": ["implemented", "rejected", "deprecated"],
                "implemented": ["verified", "rejected"],
                "verified": ["deprecated"],
                "rejected": ["proposed"],
                "deprecated": [],
            },
            "default": "proposed",
        },
        "quality": {
            "min_words": 5,
            "max_words": 300,
            "rules": {
                "weak_words": True,
                "vague_quantifiers": True,
                "passive_voice": False,
                "placeholders": True,
                "non_atomic": True,
                "untestable": True,
                "word_count": True,
            },
        },
    })

    # Build requirements
    reqs = {r["id"]: r for r in _requirements()}
    vcs = {}
    for vc in VERIFICATION_CASES:
        vcs[vc["id"]] = {**vc, "status": "pending", "result": None,
                         "verified_requirements": []}

    # Wire up VC → requirement links
    for vc_id, req_ids in VC_LINKS.items():
        vcs[vc_id]["verified_requirements"] = list(req_ids)
        for rid in req_ids:
            reqs[rid]["verification_cases"].append(vc_id)

    # Wire up requirement → requirement relations
    for src, tgt, rel_type in RELATIONS:
        reqs[src]["relations"].append({"type": rel_type, "target": tgt})

    # Add attributes for compliance tagging
    for rid in ("AFRM0000", "AFRM0001", "AFRM0005", "PROP0001", "AVNC0008"):
        _add_attr(reqs[rid], "standard", "DO-178C" if rid.startswith("AVN") else "DO-254")
    for rid in ("SAFE0000", "SAFE0001", "SAFE0003", "AD2024001"):
        _add_attr(reqs[rid], "standard", "FAR Part 23")
    _add_attr(reqs["ACFT0000"], "author", "Systems Engineering")

    # Write everything to disk
    for r in reqs.values():
        store.create_requirement(r)
    for vc in vcs.values():
        store.create_verification_case(vc)

    store.write_traces({"links": TRACES})

    for cr_data in CHANGE_REQUESTS:
        store.create_item("change_requests", {
            **{k: v for k, v in cr_data.items() if k not in ("status", "submitted_by")},
            "status": cr_data.get("status", "submitted"),
            "submitted_by": cr_data.get("submitted_by", ""),
            "reviewed_by": "",
            "approved_by": "",
        })

    for risk in RISKS:
        store.create_item("risks", {
            **{k: v for k, v in risk.items() if k not in ("status", "mitigation")},
            "impact": "",
            "status": risk.get("status", "open"),
            "mitigation": risk.get("mitigation", ""),
            "linked_requirements": [],
        })

    for c in COMMENTS:
        store.create_item("comments", {
            **{k: v for k, v in c.items() if k != "id"},
            "id": c.get("id", f"COMMENT-{uuid.uuid4().hex[:8].upper()}"),
            "resolved": c.get("resolved", False),
        })

    for d in DECISIONS:
        store.create_item("decisions", {
            **{k: v for k, v in d.items()},
        })

    return True
