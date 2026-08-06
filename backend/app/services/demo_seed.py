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
         baselines=None, allocated="", priorities=None,
         needs=None, normative=True,
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
        "baselines": baselines or [],
        "system_states": [],
        "allocated_to": allocated,
        "cascade_from": None,
        "attributes": [],
        "relations": [],
        "verification_cases": [],
        "references": references or [],
        "needs": needs or [],
        "normative": normative,
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
        baselines=["PDR"],
        needs=["design"],
        priorities={"development": 5, "customers": 5, "safety": 5},
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
        "system", "approved", "critical",
        "Structural integrity is the fundamental safety foundation"
        " of the aircraft. The Cessna 172S uses proven aluminum"
        " semi-monocoque construction for optimal strength-to-weight.",
        "FAR 23.301, Cessna DS-100",
        baselines=["PDR"],
        allocated="Airframe Team",
        needs=["design", "verification_case"],
        priorities={"development": 3, "safety": 5, "customers": 2},
    ))

    r.append(_req(
        "AFRM0000", "AFRM0001",
        "Fuselage Structure",
        "<p>The fuselage shall be a semi-monocoque aluminum alloy"
        " structure with four ergonomic seats, two forward-hinged"
        " cabin doors, and a cargo area rated for 120 lb behind"
        " the rear seats.</p>",
        "system", "approved", "high",
        "Primary occupant enclosure must withstand crash loads"
        " per FAR 23.561 while remaining lightweight.",
        "Cessna DS-110",
        allocated="Structures",
        needs=["design"],
        priorities={"development": 2, "safety": 3, "customers": 3},
    ))

    r.append(_req(
        "AFRM0001", "AFRM0002",
        "Cabin Interior & Restraints",
        "<p>The cabin shall accommodate 4 occupants with 3-point"
        " inertial-reel restraint harnesses for forward seats and"
        " fixed 3-point harnesses for rear seats. Cargo tie-down"
        " points shall withstand 9g forward loading.</p>",
        "safety", "approved", "high",
        "Occupant safety during emergency landing is paramount."
        " 3-point harnesses reduce HIC (Head Injury Criterion)"
        " vs lap belts alone.",
        "FAR 23.561, FAR 23.785",
        needs=["design", "verification_case"],
        priorities={"development": 1, "safety": 4, "customers": 3},
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
        "non_functional_usability", "approved", "high",
        "Training aircraft cockpits must minimize pilot workload."
        " The Cessna 172 tradition places flap switch and trim"
        " wheel within reach of the right hand while the left"
        " hand remains on the yoke.",
        "GAMA Publication 10, Cessna DR-420",
        allocated="Cockpit Integration",
        needs=["design"],
        priorities={"development": 2, "customers": 4, "safety": 2},
    ))

    r.append(_req(
        "AFRM0000", "AFRM0004",
        "Wing Assembly",
        "<p>The wings shall be a high-wing, strut-braced configuration"
        " using NACA 2412 airfoil with 36 ft span and 174 sq ft"
        " area. The high-wing placement shall provide excellent"
        " downward visibility for the crew and inherent lateral"
        " stability through dihedral effect.</p>",
        "system", "approved", "critical",
        "The high-wing configuration is a defining Cessna 172"
        " characteristic. It provides natural roll stability"
        " (pendulum effect), protects the cabin from sun/rain,"
        " and gives pilots exceptional ground visibility.",
        "Cessna DS-120",
        baselines=["PDR"],
        needs=["design", "verification_case"],
        priorities={"development": 3, "safety": 3, "customers": 3},
    ))

    r.append(_req(
        "AFRM0004", "AFRM0005",
        "Main Spar Ultimate Load",
        "<p>The main spar shall withstand an ultimate load factor of"
        " +3.8g and -1.52g with no permanent deformation, per"
        " FAR 23.337 limit maneuvering loads. Safety factor of 1.5"
        " shall be applied to limit loads for ultimate design.</p>",
        "non_functional_performance", "approved", "critical",
        "The main spar is the single most critical structural"
        " element. Failure is catastrophic. The 3.8g limit"
        " corresponds to the Normal Category envelope.",
        "FAR 23.337, FAR 23.305",
        needs=["verification_case"],
        priorities={"development": 2, "safety": 5},
    ))

    r.append(_req(
        "AFRM0004", "AFRM0006",
        "Integral Wing Fuel Tanks",
        "<p>Each wing shall house an integral fuel tank formed by"
        " the wing structure, sealed with polysulfide sealant,"
        " with total usable capacity of 53 US gallons (200 L)"
        " and 3 gallons unusable. Fuel quantity transmitters"
        " shall be resistive float-type per FAR 23.1337.</p>",
        "system", "approved", "high",
        "Integral (wet-wing) tanks eliminate separate bladder"
        " weight. 53 usable gallons provide ~5 hours endurance"
        " at 75% power with VFR reserves.",
        "FAR 23.963, Cessna DS-121",
        allocated="Fuel Systems",
        needs=["design", "verification_case"],
        priorities={"development": 2, "safety": 3, "customers": 2},
    ))

    r.append(_req(
        "AFRM0000", "AFRM0007",
        "Empennage",
        "<p>The empennage shall use a conventional tail arrangement"
        " with a fixed horizontal stabilizer plus movable elevator"
        " for pitch control, and a fixed vertical fin plus movable"
        " rudder for directional (yaw) control.</p>",
        "system", "approved", "high",
        baselines=["PDR"],
        needs=["design"],
        priorities={"development": 2, "safety": 2, "customers": 1},
    ))

    r.append(_req(
        "AFRM0007", "AFRM0008",
        "Horizontal Stabilizer & Elevator",
        "<p>The horizontal stabilizer shall provide static pitch"
        " stability (positive dCm/dα). The elevator shall be"
        " aerodynamically balanced with a ground-adjustable trim"
        " tab for stick-force reduction. Control forces shall"
        " not exceed 10 lb at V_A.</p>",
        "system", "approved", "medium",
        needs=["design", "verification_case"],
        priorities={"development": 1, "safety": 2},
    ))

    r.append(_req(
        "AFRM0007", "AFRM0009",
        "Vertical Fin & Rudder",
        "<p>The vertical fin shall provide static directional"
        " stability (positive Cnβ). The rudder shall be"
        " aerodynamically balanced with a ground-adjustable"
        " trim tab. Pedal forces shall not exceed 50 lb at V_A.</p>",
        "system", "approved", "medium",
        needs=["design"],
        priorities={"development": 1, "safety": 2},
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
        baselines=["PDR"],
        allocated="Powerplant Team",
        needs=["design", "verification_case"],
        priorities={"development": 3, "safety": 4, "customers": 3, "maintenance": 2},
    ))

    r.append(_req(
        "PROP0000", "PROP0001",
        "Engine — Lycoming IO-360-L2A",
        "<p>A 4-cylinder, horizontally opposed, air-cooled,"
        " fuel-injected engine with 360 cubic inch displacement,"
        " 8.5:1 compression ratio, and dual magneto ignition."
        " TBO shall be 2000 hours.</p>",
        "system", "approved", "critical",
        "The IO-360 series has over 55,000 units in service."
        " Horizontally opposed configuration minimizes frontal"
        " area and provides natural primary balance.",
        "Lycoming IO-360 Operator's Manual",
        allocated="Engine Integration",
        needs=["design", "verification_case"],
        priorities={"development": 2, "safety": 4, "maintenance": 3},
    ))

    r.append(_req(
        "PROP0001", "PROP0002",
        "Precision Fuel Injection",
        "<p>The fuel injection system shall deliver a stoichiometric"
        " air-fuel mixture (14.7:1 ± 0.5) across the operating"
        " range from idle (600 RPM) to full power (2700 RPM),"
        " with mixture control adjustable by the pilot via a"
        " vernier control cable.</p>",
        "functional", "implemented", "high",
        "Precision fuel injection eliminates the carburetor icing"
        " hazard and provides cylinder-to-cylinder mixture balance"
        " within 0.5 GPH, improving efficiency and reducing CHT"
        " spread.",
        "Lycoming Service Instruction 1427",
        needs=["design"],
        priorities={"development": 2, "safety": 3, "maintenance": 1},
    ))

    r.append(_req(
        "PROP0001", "PROP0003",
        "Dual Magneto Ignition",
        "<p>Two independent magnetos (Slick 4370/4371 or Bendix"
        " S4LN-20/S4LN-21), each firing one spark plug per"
        " cylinder, shall provide redundant ignition circuits."
        " The left magneto shall fire the bottom plugs; the right"
        " magneto shall fire the top plugs.</p>",
        "non_functional_reliability", "approved", "critical",
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
        priorities={"development": 2, "safety": 5},
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
        priorities={"development": 1, "customers": 3, "maintenance": 3},
    ))

    r.append(_req(
        "PROP0000", "PROP0005",
        "Propeller — McCauley 1A170/E",
        "<p>A McCauley 2-blade fixed-pitch aluminium-alloy propeller,"
        " 76-inch diameter, with a pitch of 60 inches (climb"
        " optimised).  The propeller shall produce a static thrust"
        " of at least 550 lbf at sea level, ISA conditions.</p>",
        "system", "approved", "high",
        "Fixed-pitch propeller is simpler, lighter, and cheaper"
        " than constant-speed, suiting the training/rental market."
        "  The 76-inch diameter is the maximum for ground clearance"
        " on the tricycle-gear 172, and the 60-inch pitch provides"
        " a good climb/cruise compromise for the 180 BHP engine.",
        "McCauley TCDS P-874",
        allocated="Powerplant",
        needs=["verification_case"],
        priorities={"development": 1, "customers": 3, "safety": 2},
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
        baselines=["CDR"],
        allocated="Fuel Systems",
        needs=["design", "verification_case"],
        priorities={"development": 2, "safety": 5, "maintenance": 2},
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
        baselines=["CDR"],
        allocated="Avionics Integration",
        needs=["design", "verification_case"],
        priorities={"development": 4, "customers": 5, "safety": 3},
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
        priorities={"development": 2, "safety": 4, "customers": 4},
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
        priorities={"development": 2, "customers": 4, "safety": 3},
    ))

    # Decision record for G1000 NXi selection
    r.append(_req(
        "AVNC0000", "AVNC0010",
        "Avionics Architecture Decision",
        "<p>The Garmin G1000 NXi was selected as the integrated"
        " avionics platform.  This decision was recorded per the"
        " system engineering decision process.</p>",
        "system", "approved", "medium",
        "Decision record: G1000 NXi vs G1000 vs G500 TXi trade"
        " study concluded the NXi provides the best balance of"
        " capability (WAAS/SBAS LPV), installed cost, and"
        " familiarity for the training fleet market.",
        "Systems Engineering Decision Log",
        normative=False,
        needs=[],
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
        priorities={"development": 3, "safety": 4, "customers": 3},
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
        priorities={"development": 2, "safety": 5},
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
        "functional", "verified", "high",
        "While GPS is the primary navigation source, VOR/ILS"
        " provides a dissimilar-technology backup that is immune"
        " to GPS jamming/outages.  ILS capability also enables"
        " training for the instrument rating practical test.",
        "TSO-C36e, TSO-C40c",
        needs=["design"],
        priorities={"development": 1, "safety": 3, "customers": 2},
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
        priorities={"development": 2, "safety": 3, "customers": 3},
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
        priorities={"development": 1, "customers": 2},
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
        priorities={"development": 2, "safety": 5, "customers": 4},
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
        priorities={"development": 1, "customers": 3},
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
        baselines=["PDR"],
        allocated="Flight Controls Team",
        needs=["design", "verification_case"],
        priorities={"development": 3, "safety": 5, "customers": 2},
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
        priorities={"development": 2, "safety": 5},
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
        "system", "approved", "high",
        "Differential aileron throw is the primary adverse-yaw"
        " mitigation technique on the Cessna 172.  More up-travel"
        " than down-travel increases drag on the up-going wing,"
        " offsetting the induced-drag asymmetry.  Combined with"
        " the Frise nose this produces a proverse yaw moment that"
        " reduces the need for coordinated rudder input.",
        needs=["design", "verification_case"],
        priorities={"development": 2, "safety": 3},
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
        "system", "approved", "high",
        "Push-pull tubes provide precise elevator control without"
        " cable stretch or temperature effects.  The anti-servo"
        " tab moves in the same direction as the elevator,"
        " providing a linear trim-force gradient that pilots"
        " find intuitive.",
        needs=["design"],
        priorities={"development": 2, "safety": 3},
    ))

    r.append(_req(
        "FLTC0001", "FLTC0004",
        "Rudder Control",
        "<p>Cable-actuated rudder with adjustable pedal positions"
        " (3 positions by pin selection).  Rudder travel shall be"
        " ±24° ±2°.  A ground-adjustable trim tab shall provide"
        " cruise rudder trim for hands-off coordinated flight"
        " at typical cruise power settings (2400 RPM, leaned).</p>",
        "system", "approved", "medium",
        needs=["design"],
        priorities={"development": 1, "safety": 2, "customers": 2},
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
        priorities={"development": 2, "safety": 3, "customers": 3},
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
        "system", "approved", "high",
        "Electric flaps reduce pilot workload versus manual (Johnson"
        " bar) flaps, freeing the right hand for throttle and"
        " mixture adjustment during the approach.  The detent"
        " positions eliminate the need for the pilot to judge"
        " intermediate settings.",
        allocated="Electrical Integration",
        needs=["design"],
        priorities={"development": 1, "safety": 2},
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
        "system", "approved", "medium",
        "The split trim switch (both halves must be pressed together)"
        " prevents inadvertent activation from accidental contact."
        "  Electric trim reduces pilot fatigue on longer flights"
        " but the manual wheel provides a reliable mechanical"
        " baseline and is used as the primary means of trimming.",
        needs=["design"],
        priorities={"development": 1, "customers": 3},
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
        "system", "approved", "critical",
        "Fixed gear is chosen for simplicity, lower weight, and"
        " elimination of the retraction mechanism failure modes."
        "  Spring steel legs provide excellent energy absorption"
        " and are virtually maintenance-free compared to oleo"
        " struts.",
        baselines=["CDR"],
        allocated="Landing Gear Team",
        needs=["design", "verification_case"],
        priorities={"development": 2, "safety": 3, "maintenance": 3},
    ))

    r.append(_req(
        "LNDG0000", "LNDG0001",
        "Main Gear Legs & Wheels",
        "<p>Tubular spring steel (6150 chrome-vanadium) main gear"
        " legs, heat-treated to 44-48 HRC, shall attach to the"
        " fuselage at forged aluminium bulkhead fittings.  Wheels"
        " shall be Cleveland 40-77B 6.00-6 with 6-ply tyres rated"
        " to 100 mph.  The track shall be 8 ft 4.5 in.</p>",
        "system", "approved", "high",
        needs=["design"],
        priorities={"development": 1, "safety": 2},
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
        "system", "approved", "high",
        "The steerable nosewheel tied to rudder pedals gives the"
        " pilot intuitive ground steering — the same foot motion"
        " used for yaw control in flight.  The shimmy damper is"
        " a wear item requiring inspection every 100 hours; its"
        " design as a sealed hydraulic unit minimizes maintenance.",
        needs=["design"],
        priorities={"development": 1, "safety": 2, "maintenance": 2},
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
        priorities={"development": 1, "safety": 4},
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
        baselines=["CDR"],
        allocated="Electrical Systems",
        needs=["design", "verification_case"],
        priorities={"development": 2, "safety": 4, "maintenance": 2},
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
        "system", "approved", "high",
        needs=["design"],
        priorities={"development": 2, "safety": 2},
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
        "safety", "approved", "critical",
        "SLA batteries eliminate acid spill risk and maintenance"
        " requirements.  30 minutes of essential bus power at a"
        " 15 A load provides sufficient endurance to reach an"
        " airport in an alternator-out scenario in the traffic"
        " pattern (worst case).",
        needs=["verification_case"],
        priorities={"development": 1, "safety": 4},
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
        "non_functional_reliability", "approved", "high",
        needs=["design"],
        priorities={"development": 2, "safety": 3},
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
        priorities={"development": 1, "maintenance": 2},
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
        baselines=["CDR"],
        needs=["design"],
        priorities={"development": 1, "customers": 4, "safety": 1},
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
        priorities={"development": 1, "safety": 4, "customers": 3},
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
        priorities={"development": 1, "customers": 3},
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
        priorities={"development": 1, "safety": 5},
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
        priorities={"development": 2, "safety": 5, "customers": 3},
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
        priorities={"development": 1, "safety": 5},
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
        priorities={"development": 1, "safety": 5},
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
        priorities={"development": 1, "safety": 5},
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
        priorities={"development": 1, "customers": 2, "safety": 3},
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
        "regulatory_compliance", "approved", "critical",
        "This AD was prompted by NTSB Safety Recommendation A-22-3"
        " following multiple CO-related incidents in general"
        " aviation.  Mandatory compliance is required for"
        " continued airworthiness.",
        "FAA AD 2024-01-05, NTSB A-22-3",
        needs=["design"],
        priorities={"safety": 5, "maintenance": 3},
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
        "system", "approved", "low",
        normative=False,
        needs=[],
        priorities={},
    ))

    return r


# ── verification cases ────────────────────────────────────────────────────────

VERIFICATION_CASES = [
    # passed — completed successfully
    {"id": "VCAF0001", "name": "Structural Static Test", "method": "test",
     "description": "Static load test of airframe to ultimate load per FAR 23.305",
     "status": "passed", "result": "All test points passed. Ultimate load sustained with no permanent deformation."},
    {"id": "VCPR0001", "name": "Engine Run-Up Test", "method": "test",
     "description": "Full-power engine run at 2700 RPM, magneto drop check, fuel flow verification",
     "status": "passed", "result": "2700 RPM achieved, mag drop 125 RPM (limit 150), fuel flow 15.4 GPH."},
    {"id": "VCSF0001", "name": "Stall Warning Calibration", "method": "test",
     "description": "Stall warning horn activation verified 5-10 kn above stall in all configs",
     "status": "passed", "result": "Horn activated at 55 KCAS (clean), 7 kn margin. All configs within spec."},
    {"id": "VCPR0004", "name": "Fuel Injection Calibration", "method": "test",
     "description": "Verify fuel flow balance within 0.5 GPH across all cylinders at 75 % power",
     "status": "passed", "result": "Max imbalance 0.3 GPH across cylinders at 75 % power. Within 0.5 GPH limit."},

    # failed — landed on a non-SRR requirement so it does not contradict frozen SRR
    {"id": "VCAV0002", "name": "ADS-B Compliance Test", "method": "test",
     "description": "ADS-B Out performance verification per 14 CFR 91.227, DO-260B",
     "status": "failed", "result": "NIC dropped below 7 at low altitude due to GPS antenna masking. Re-test required."},

    # in_progress
    {"id": "VCPR0002", "name": "Fuel System Flow Test", "method": "test",
     "description": "Fuel flow test at all flight attitudes and power settings per FAR 23.955",
     "status": "in_progress"},
    {"id": "VCEV0001", "name": "CO Detector Validation", "method": "test",
     "description": "CO detector activation at 50 ±10 ppm, aural/visual alert verified",
     "status": "in_progress"},

    # pending — not yet started
    {"id": "VCAF0002", "name": "Crashworthiness Analysis", "method": "analysis",
     "description": "FAR 23.561 emergency landing dynamic FEA analysis"},
    {"id": "VCAV0001", "name": "Avionics Integration Test", "method": "test",
     "description": "End-to-end G1000 NXi integration test: PFD/MFD/ADAHRS/GPS/COM"},
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
    {"id": "VCSF0002", "name": "ELT Functional Test", "method": "test",
     "description": "406 MHz ELT activation test per TSO-C126b, G-switch threshold verified"},
    {"id": "VCCB0001", "name": "Brake Holding Test", "method": "test",
     "description": "Parking brake holding force verified at full static run-up (1800 RPM)"},
    {"id": "VCPR0003", "name": "Propeller Balance Test", "method": "test",
     "description": "Dynamic balance of propeller assembly to ≤0.2 IPS per SAE ARP 4162"},
    {"id": "VCAV0003", "name": "VHF COM Range Test", "method": "test",
     "description": "Voice quality and range test: 100 NM at 5000 ft AGL per TSO-C169a"},
    {"id": "VCEL0003", "name": "Emergency Power Transfer Test", "method": "test",
     "description": "Essential bus transfer < 10 ms during alternator failure; battery-only endurance ≥ 30 min"},
    {"id": "VCFC0003", "name": "Pitch Trim Range Test", "method": "inspection",
     "description": "Full trim wheel travel verified: ±30 lb stick force relief at all speeds"},
    {"id": "VCLG0001", "name": "Nose Gear Shimmy Test", "method": "test",
     "description": "Nose gear damping verification: no sustained shimmy at 0-40 kn taxi speeds"},
    {"id": "VCEN0001", "name": "Cabin Temperature Profile", "method": "analysis",
     "description": "FEA cabin temperature distribution with OAT -18 °C, heat full on"},
    {"id": "VCAF0003", "name": "Fuel Tank Leak Test", "method": "test",
     "description": "Integral wing tank pressurised to 3.5 psi submerged, zero leakage in 10 min per FAR 23.965"},
    {"id": "VCLG0002", "name": "Brake Energy Absorption", "method": "analysis",
     "description": "Kinetic energy capacity verification for rejected takeoff at MTOW 1157 kg"},
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
    "VCPR0003": ["PROP0005"],
    "VCPR0004": ["PROP0002"],
    "VCAV0003": ["AVNC0007"],
    "VCEL0003": ["ELEC0002", "ELEC0003"],
    "VCFC0003": ["FLTC0007"],
    "VCLG0001": ["LNDG0002"],
    "VCEN0001": ["ENVR0001"],
    "VCAF0003": ["AFRM0006"],
    "VCLG0002": ["LNDG0003"],
}

# ── components (the synthesised design) ───────────────────────────────────────
# A physical breakdown with mass and current-draw parameters, so the demo's
# budget rollups (`rollup('C172', 'mass')`, `rollup('AVIO', 'current')`) have
# a real tree to sum over. Masses are per-unit; `quantity` multiplies.


def _comp(cid, name, ctype, parent, desc="", part_number="", supplier="",
          quantity=1, satisfies=None, verification_cases=None, parameters=None,
          baselines=None):
    return {
        "id": cid, "name": name, "description": desc, "type": ctype,
        "parent": parent, "part_number": part_number, "supplier": supplier,
        "quantity": quantity, "satisfies": satisfies or [],
        "verification_cases": verification_cases or [],
        "attributes": [], "parameters": parameters or [],
        "baselines": baselines or [],
    }


def _p(name, value, unit):
    return {"name": name, "value": value, "unit": unit, "expr": None}


COMPONENTS = [
    # ═════════════════════════════════════════════════════════════════════════
    # Cessna 172S Skyhawk SP — Complete Physical Breakdown
    #
    # Hierarchy: system → assembly → part (with quantity for multiple instances)
    # Each line: satisfies the requirement it realises; carries mass for the
    # empty-weight rollup; avionics parts also carry current draw for the
    # electrical load budget.
    # ═════════════════════════════════════════════════════════════════════════

    # ── Top-level system ───────────────────────────────────────────────────
    _comp("C172", "Cessna 172S Skyhawk SP", "system", None,
          desc="Top of the physical breakdown. The empty-weight budget and electrical load roll up from here.",
          satisfies=["ACFT0000"]),

    # ── AIRFRAME ───────────────────────────────────────────────────────────
    _comp("FUSE", "Fuselage", "assembly", "C172",
          satisfies=["AFRM0001"], parameters=[_p("mass", 181, "kg")]),
    _comp("COCK", "Cockpit", "assembly", "FUSE",
          satisfies=["AFRM0003"], parameters=[_p("mass", 14, "kg")]),
    _comp("YOKE", "Control Yoke", "part", "COCK", quantity=2,
          part_number="MC1660102-1", supplier="Cessna",
          satisfies=["FLTC0001"], parameters=[_p("mass", 3.1, "kg")]),
    _comp("PEDL", "Rudder Pedal Assembly", "part", "COCK", quantity=2,
          satisfies=["FLTC0004"], parameters=[_p("mass", 2.4, "kg")]),
    _comp("IPAN", "Instrument Panel", "part", "COCK",
          part_number="MC1660400-15", supplier="Cessna",
          satisfies=["AFRM0003"], parameters=[_p("mass", 7.2, "kg")]),
    _comp("SEAT", "Crew Seat", "part", "FUSE", quantity=2,
          part_number="0713500-2", supplier="Amsafe",
          satisfies=["AFRM0002"], parameters=[_p("mass", 8.5, "kg")]),
    _comp("RSEAT", "Rear Passenger Seat", "part", "FUSE", quantity=2,
          satisfies=["AFRM0002"], parameters=[_p("mass", 6.8, "kg")]),
    _comp("HARN", "3-Point Restraint Harness", "part", "FUSE", quantity=4,
          satisfies=["AFRM0002"], parameters=[_p("mass", 0.9, "kg")]),
    _comp("DOOR", "Cabin Door", "part", "FUSE", quantity=2,
          satisfies=["AFRM0001"], parameters=[_p("mass", 7.3, "kg")]),

    _comp("WING", "Wing Assembly", "assembly", "C172",
          satisfies=["AFRM0004"], parameters=[_p("mass", 48, "kg")]),
    _comp("SPAR", "Main Spar", "part", "WING", quantity=2,
          part_number="0523001-2", supplier="Cessna",
          satisfies=["AFRM0005"], verification_cases=["VCAF0001"],
          parameters=[_p("mass", 19, "kg")]),
    _comp("ASPAR", "Aft Spar", "part", "WING", quantity=2,
          satisfies=["AFRM0004"], parameters=[_p("mass", 4.6, "kg")]),
    _comp("TANK", "Integral Fuel Tank", "part", "WING", quantity=2,
          satisfies=["AFRM0006"], verification_cases=["VCFL0001"],
          parameters=[_p("mass", 9, "kg")]),
    _comp("FQSND", "Fuel Quantity Sender", "part", "TANK", quantity=2,
          part_number="C661003-0101", supplier="Ametek",
          satisfies=["AFRM0006"], parameters=[_p("mass", 0.3, "kg")]),
    _comp("STRT", "Wing Strut", "part", "WING", quantity=2,
          part_number="0523605-1", supplier="Cessna",
          satisfies=["AFRM0004"], parameters=[_p("mass", 4.1, "kg")]),

    _comp("EMP", "Empennage", "assembly", "C172",
          satisfies=["AFRM0007"], parameters=[_p("mass", 27, "kg")]),
    _comp("HSTB", "Horizontal Stabilizer", "part", "EMP",
          satisfies=["AFRM0008"], parameters=[_p("mass", 7.8, "kg")]),
    _comp("ELEV", "Elevator", "part", "HSTB",
          satisfies=["AFRM0008", "FLTC0003"], parameters=[_p("mass", 3.5, "kg")]),
    _comp("VFIN", "Vertical Fin", "part", "EMP",
          satisfies=["AFRM0009"], parameters=[_p("mass", 5.2, "kg")]),
    _comp("RUDD", "Rudder", "part", "VFIN",
          satisfies=["AFRM0009", "FLTC0004"], parameters=[_p("mass", 2.9, "kg")]),

    # ── LANDING GEAR ───────────────────────────────────────────────────────
    _comp("GEAR", "Landing Gear", "assembly", "C172",
          satisfies=["LNDG0000"], parameters=[_p("mass", 52, "kg")]),
    _comp("MLEG", "Main Gear Leg", "part", "GEAR", quantity=2,
          part_number="0543012-2", supplier="Cessna",
          satisfies=["LNDG0001"], parameters=[_p("mass", 10.8, "kg")]),
    _comp("MWHE", "Main Wheel Assembly", "part", "MLEG", quantity=2,
          part_number="40-77B", supplier="Cleveland",
          satisfies=["LNDG0001"], parameters=[_p("mass", 3.9, "kg")]),
    _comp("BRAK", "Brake Caliper", "part", "MWHE", quantity=2,
          part_number="30-52", supplier="Cleveland",
          satisfies=["LNDG0003"], parameters=[_p("mass", 1.1, "kg")]),
    _comp("NLEG", "Nose Gear Strut", "part", "GEAR",
          part_number="0542007-1", supplier="Cessna",
          satisfies=["LNDG0002"], parameters=[_p("mass", 6.4, "kg")]),
    _comp("SMDM", "Shimmy Damper", "part", "NLEG",
          part_number="0440011-1", supplier="Cessna",
          satisfies=["LNDG0002"], parameters=[_p("mass", 0.6, "kg")]),

    # ── POWERPLANT ─────────────────────────────────────────────────────────
    _comp("ENG", "IO-360-L2A Engine", "part", "C172",
          part_number="IO-360-L2A", supplier="Lycoming",
          satisfies=["PROP0001"], verification_cases=["VCPR0001"],
          parameters=[_p("mass", 88, "kg")]),
    _comp("FISV", "Fuel Injection Servo", "part", "ENG",
          part_number="LW-15794", supplier="Precision Airmotive",
          satisfies=["PROP0002"], parameters=[_p("mass", 1.4, "kg")]),
    _comp("FDIV", "Flow Divider", "part", "ENG",
          part_number="LW-15795", supplier="Precision Airmotive",
          satisfies=["PROP0002"], parameters=[_p("mass", 0.5, "kg")]),
    _comp("LMAG", "Left Magneto", "part", "ENG",
          part_number="4370", supplier="Slick",
          satisfies=["PROP0003"], parameters=[_p("mass", 1.8, "kg")]),
    _comp("RMAG", "Right Magneto", "part", "ENG",
          part_number="4371", supplier="Slick",
          satisfies=["PROP0003"], parameters=[_p("mass", 1.8, "kg")]),
    _comp("MUFF", "Muffler / Heat Exchanger", "part", "ENG",
          part_number="0450333-1", supplier="Cessna",
          satisfies=["ENVR0001"], parameters=[_p("mass", 3.2, "kg")]),
    _comp("OILS", "Oil Sump & Cooler", "part", "ENG",
          satisfies=["PROP0001"], parameters=[_p("mass", 3.8, "kg")]),
    _comp("EMNT", "Engine Mount", "part", "C172",
          satisfies=["PROP0000"], parameters=[_p("mass", 4.5, "kg")]),

    _comp("PRPL", "Fixed-Pitch Propeller", "part", "C172",
          part_number="1A170E/JHA7660", supplier="McCauley",
          satisfies=["PROP0005"], parameters=[_p("mass", 17, "kg")]),
    _comp("SPIN", "Propeller Spinner", "part", "PRPL",
          part_number="C163023-0101", supplier="McCauley",
          satisfies=["PROP0005"], parameters=[_p("mass", 0.8, "kg")]),

    # ── FUEL SYSTEM ────────────────────────────────────────────────────────
    _comp("FUEL", "Fuel System", "assembly", "C172",
          satisfies=["PROP0006"], parameters=[_p("mass", 6, "kg")]),
    _comp("FSEL", "Fuel Selector Valve", "part", "FUEL",
          part_number="0413135-1", supplier="Cessna",
          satisfies=["PROP0006"], parameters=[_p("mass", 0.7, "kg")]),
    _comp("BPMP", "Electric Boost Pump", "part", "FUEL",
          part_number="5100-00-3", supplier="Dukes",
          satisfies=["PROP0006", "ELEC0000"],
          parameters=[_p("mass", 1.1, "kg"), _p("current", 3.5, "A")]),
    _comp("EPMP", "Engine-Driven Fuel Pump", "part", "FUEL",
          part_number="LW-15473", supplier="Precision Airmotive",
          satisfies=["PROP0006"], parameters=[_p("mass", 0.8, "kg")]),
    _comp("GCOL", "Gascolator / Strainer", "part", "FUEL",
          part_number="C269501-0102", supplier="Cessna",
          satisfies=["PROP0006"], parameters=[_p("mass", 0.4, "kg")]),

    # ── AVIONICS ───────────────────────────────────────────────────────────
    _comp("AVIO", "G1000 NXi Avionics Suite", "subsystem", "C172",
          desc="Trays, harness and LRUs; the current rollup feeds the electrical load rule.",
          satisfies=["AVNC0000"], parameters=[_p("mass", 4, "kg")]),
    _comp("GDU", "GDU 1050 Display Unit", "part", "AVIO", quantity=2,
          part_number="GDU-1050", supplier="Garmin",
          satisfies=["AVNC0001", "AVNC0002"], verification_cases=["VCAV0001"],
          parameters=[_p("mass", 3.2, "kg"), _p("current", 3.5, "A")]),
    _comp("GIA", "GIA 64W Integrated Avionics Unit", "part", "AVIO", quantity=2,
          part_number="GIA-64W", supplier="Garmin",
          satisfies=["AVNC0004", "AVNC0005", "AVNC0007"],
          parameters=[_p("mass", 2.8, "kg"), _p("current", 4.9, "A")]),
    _comp("GDC", "GDC 74A Air Data Computer", "part", "AVIO",
          part_number="GDC-74A", supplier="Garmin",
          satisfies=["AVNC0001"], parameters=[_p("mass", 0.9, "kg"), _p("current", 0.4, "A")]),
    _comp("GRS", "GRS 79 ADAHRS", "part", "AVIO",
          part_number="GRS-79", supplier="Garmin",
          satisfies=["AVNC0001"], parameters=[_p("mass", 1.1, "kg"), _p("current", 0.6, "A")]),
    _comp("GMU", "GMU 44 Magnetometer", "part", "AVIO",
          part_number="GMU-44", supplier="Garmin",
          satisfies=["AVNC0003"], parameters=[_p("mass", 0.3, "kg"), _p("current", 0.1, "A")]),
    _comp("GEA", "GEA 71B Engine/Airframe Unit", "part", "AVIO",
          part_number="GEA-71B", supplier="Garmin",
          satisfies=["PROP0004"], parameters=[_p("mass", 0.7, "kg"), _p("current", 0.3, "A")]),
    _comp("GTX", "GTX 345R Mode S Transponder", "part", "AVIO",
          part_number="GTX-345R", supplier="Garmin",
          satisfies=["AVNC0008"], verification_cases=["VCAV0002"],
          parameters=[_p("mass", 1.6, "kg"), _p("current", 1.7, "A")]),
    _comp("GMA", "GMA 1360 Audio Panel", "part", "AVIO",
          part_number="GMA-1360", supplier="Garmin",
          satisfies=["AVNC0009"],
          parameters=[_p("mass", 0.9, "kg"), _p("current", 0.6, "A")]),

    # ── ELECTRICAL ─────────────────────────────────────────────────────────
    _comp("ELEC", "Electrical System", "subsystem", "C172",
          satisfies=["ELEC0000"], parameters=[_p("mass", 3, "kg")]),
    _comp("ALT", "60 A Alternator", "part", "ELEC",
          part_number="ALX-9521R", supplier="Plane-Power",
          satisfies=["ELEC0001"], verification_cases=["VCEL0001"],
          parameters=[_p("mass", 5, "kg")]),
    _comp("VREG", "Solid-State Voltage Regulator", "part", "ALT",
          satisfies=["ELEC0001"], parameters=[_p("mass", 0.3, "kg")]),
    _comp("BATT", "24 V 13.6 Ah Sealed Battery", "part", "ELEC",
          part_number="RG-243", supplier="Concorde",
          satisfies=["ELEC0002"], verification_cases=["VCEL0002"],
          parameters=[_p("mass", 13, "kg")]),
    _comp("MBUS", "Main Bus Panel", "part", "ELEC",
          satisfies=["ELEC0003"], parameters=[_p("mass", 1.2, "kg")]),
    _comp("EBUS", "Essential Bus Relay", "part", "ELEC",
          satisfies=["ELEC0003"], parameters=[_p("mass", 0.5, "kg")]),
    _comp("EPOW", "External Power Receptacle", "part", "ELEC",
          part_number="MS3506-1", supplier="Amphenol",
          satisfies=["ELEC0004"], parameters=[_p("mass", 0.2, "kg")]),

    # ── FLIGHT CONTROLS ────────────────────────────────────────────────────
    _comp("FLTC", "Flight Control System", "assembly", "C172",
          satisfies=["FLTC0000"], parameters=[_p("mass", 18, "kg")]),
    _comp("AILR", "Aileron Assembly", "part", "FLTC", quantity=2,
          satisfies=["FLTC0002"], verification_cases=["VCFC0001"],
          parameters=[_p("mass", 2.7, "kg")]),
    _comp("ELVC", "Elevator Assembly", "part", "FLTC",
          satisfies=["FLTC0003"], parameters=[_p("mass", 3.5, "kg")]),
    _comp("FLAP", "Flap Assembly", "part", "FLTC", quantity=2,
          satisfies=["FLTC0006"], parameters=[_p("mass", 2.1, "kg")]),
    _comp("FLAPM", "Flap Motor", "part", "FLAP",
          part_number="C292501-0101", supplier="Cessna",
          satisfies=["FLTC0005", "ELEC0000"],
          parameters=[_p("mass", 1.4, "kg"), _p("current", 4.5, "A")]),
    _comp("TRIM", "Pitch Trim Wheel Assembly", "assembly", "FLTC",
          satisfies=["FLTC0007"], parameters=[_p("mass", 1.2, "kg")]),
    _comp("TRSV", "Pitch Trim Servo", "part", "TRIM",
          satisfies=["FLTC0007", "ELEC0000"],
          parameters=[_p("mass", 0.4, "kg"), _p("current", 0.8, "A")]),

    # ── ENVIRONMENTAL ──────────────────────────────────────────────────────
    _comp("ENVR", "Environmental Control", "assembly", "C172",
          satisfies=["ENVR0000"], parameters=[_p("mass", 5, "kg")]),
    _comp("SHUD", "Heat Exchanger Shroud", "part", "ENVR",
          satisfies=["ENVR0001"], parameters=[_p("mass", 2.1, "kg")]),
    _comp("BVAL", "Cabin Heat Butterfly Valve", "part", "ENVR",
          satisfies=["ENVR0001"], parameters=[_p("mass", 0.3, "kg")]),
    _comp("DFRS", "Defroster Plenum", "part", "ENVR",
          satisfies=["ENVR0003"], parameters=[_p("mass", 0.8, "kg")]),
    _comp("AVNT", "Fresh Air Vent", "part", "ENVR", quantity=3,
          satisfies=["ENVR0002"], parameters=[_p("mass", 0.2, "kg")]),

    # ── SAFETY SYSTEMS ─────────────────────────────────────────────────────
    _comp("SAFE", "Safety Systems", "subsystem", "C172",
          satisfies=["SAFE0000"], parameters=[_p("mass", 6, "kg")]),
    _comp("SWRN", "Pneumatic Stall Warning Horn", "part", "SAFE",
          satisfies=["SAFE0001"], verification_cases=["VCSF0001"],
          parameters=[_p("mass", 0.3, "kg")]),
    _comp("FDTC", "Fire Detection Thermocouple", "part", "SAFE",
          satisfies=["SAFE0002"], parameters=[_p("mass", 0.1, "kg")]),
    _comp("ELT", "Emergency Locator Transmitter", "part", "SAFE",
          part_number="ME406", supplier="Artex",
          satisfies=["SAFE0003"], verification_cases=["VCSF0002"],
          parameters=[_p("mass", 1.4, "kg")]),
    _comp("NAVL", "Navigation Light (Wingtip)", "part", "SAFE", quantity=2,
          part_number="A650-14", supplier="Whelen",
          satisfies=["SAFE0004"], parameters=[_p("mass", 0.2, "kg"), _p("current", 0.8, "A")]),
    _comp("TAIL", "Tail Navigation Light", "part", "SAFE",
          satisfies=["SAFE0004"], parameters=[_p("mass", 0.2, "kg"), _p("current", 0.4, "A")]),
    _comp("BCON", "Anti-Collision Beacon", "part", "SAFE",
          satisfies=["SAFE0004"], parameters=[_p("mass", 0.4, "kg"), _p("current", 1.2, "A")]),
    _comp("STRB", "Wingtip Strobe Light", "part", "SAFE", quantity=2,
          satisfies=["SAFE0004"], parameters=[_p("mass", 0.3, "kg"), _p("current", 1.5, "A")]),
    _comp("TAXI", "Landing / Taxi Light", "part", "SAFE",
          part_number="PAR-46", supplier="Whelen",
          satisfies=["SAFE0004"], parameters=[_p("mass", 0.5, "kg"), _p("current", 4.5, "A")]),

    # ── CO DETECTOR (FROM AIRWORTHINESS DIRECTIVE) ─────────────────────────
    _comp("CODT", "Active CO Detector", "part", "SAFE",
          part_number="CO-200", supplier="Guardian Avionics",
          satisfies=["AD2024001", "ENVR0001"], verification_cases=["VCEV0001"],
          parameters=[_p("mass", 0.15, "kg"), _p("current", 0.05, "A")]),
]

# ── specifications ────────────────────────────────────────────────────────────
# Two levels: the system spec collects the top-level requirements and owns the
# avionics spec as a child, so the Specifications page shows a real breakdown.

SPECIFICATIONS = [
    {"id": "SPEC-SYS", "name": "System Requirements Specification",
     "description": "Top-level specification for the complete aircraft;"
                    " decomposes into subsystem specifications.",
     "requirements": ["ACFT0000", "AFRM0000", "PROP0000", "AVNC0000",
                      "FLTC0000", "LNDG0000", "ELEC0000", "ENVR0000",
                      "SAFE0000"],
     "components": ["FUSE", "WING", "EMP", "GEAR", "ENG", "PRPL", "FUEL",
                     "AVIO", "ELEC", "FLTC", "ENVR", "SAFE"],
     "children": ["SPEC-AVIO"]},
    {"id": "SPEC-AVIO", "name": "Avionics Subsystem Specification",
     "description": "G1000 NXi avionics suite requirements, refined from"
                    " AVNC0000 in SPEC-SYS.",
     "requirements": ["AVNC0001", "AVNC0002", "AVNC0003", "AVNC0004",
                      "AVNC0005", "AVNC0006", "AVNC0007", "AVNC0008",
                      "AVNC0009", "AVNC0010"],
     "components": ["GDU", "GIA", "GDC", "GRS", "GMU", "GEA", "GTX", "GMA"],
     "children": []},
]

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

    # New cross-system relationships
    ("PROP0001", "AFRM0001", "satisfies"),       # Engine mass affects fuselage design
    ("AVNC0001", "AVNC0002", "duplicates"),       # PFD and MFD share same GDU hardware
    ("PROP0005", "PROP0001", "satisfies"),        # Propeller must match engine power rating
    ("FLTC0003", "FLTC0007", "depends"),          # Elevator control depends on trim system
    ("ELEC0002", "ELEC0001", "satisfies"),        # Battery provides backup when alternator offline
    ("LNDG0003", "LNDG0001", "refines"),          # Braking system is part of main gear
    ("AVNC0003", "AVNC0000", "satisfies"),        # Navigation fulfils avionics mission
    ("ENVR0002", "ENVR0001", "depends"),          # Ventilation depends on cabin heat ducting
    ("SAFE0002", "PROP0001", "satisfies"),        # Fire detection monitors engine bay
    ("AFRM0006", "PROP0006", "satisfies"),        # Wing tanks satisfy fuel storage need
    ("FLTC0005", "FLTC0001", "refines"),          # Flaps are part of primary flight controls
    ("ELEC0003", "PROP0003", "satisfies"),        # Bus powers magneto impulse coupling
    ("LNDG0002", "FLTC0004", "satisfies"),        # Nose gear steering aids rudder control
    ("AVNC0008", "AVNC0000", "satisfies"),        # ADS-B fulfils avionics surveillance need
    ("SAFE0001", "AFRM0004", "derives"),          # Stall horn placement derives from wing geometry

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
     "affected_components": ["ENG", "PRPL"],
     "status": "submitted", "submitted_by": "Powerplant Lead"},
    {"id": "CR000002", "title": "Landing Gear Corrosion Inspection",
     "description": "Add 100-hour corrosion inspection interval for spring steel main gear"
                    " legs, particularly at the forged attachment fitting interface where"
                    " paint wear can expose bare metal.",
     "affected_requirements": ["LNDG0001"],
     "affected_components": ["MLEG"],
     "status": "in_review", "submitted_by": "Maintenance Engineering"},
    {"id": "CR000003", "title": "LED Exterior Lighting Retrofit",
     "description": "Authorise LED replacement for all exterior lights as an owner-performed"
                    " preventive maintenance item.  LED bulbs reduce electrical load from 12 A"
                    " to 3.5 A, extending alternator and battery life.",
     "affected_requirements": ["SAFE0004", "ELEC0000"],
     "affected_components": ["NAVL", "TAIL", "BCON", "STRB", "TAXI"],
     "status": "submitted", "submitted_by": "Electrical Systems"},
    {"id": "CR000004", "title": "USB-C Charging Ports",
     "description": "Install dual USB-C (60W PD) charging ports in the cockpit for pilot"
                    " and co-pilot electronic flight bags (EFBs).  Requires circuit breaker"
                    " addition to the main bus and a supplemental type certificate (STC).",
     "affected_requirements": ["ELEC0003", "AFRM0003"],
     "affected_components": ["MBUS"],
     "status": "submitted", "submitted_by": "Avionics Integration"},
]

# ── risks ─────────────────────────────────────────────────────────────────────

RISKS = [
    # Rated through the project risk matrix: severity x likelihood -> band, derived
    # on read (see services/risk_matrix.py). `likelihood` is the five-band scale the
    # matrix indexes; the free-text `probability` these carried predates it and only
    # survives through a compatibility mapping, so it is not what a demo should show.
    #
    # linked_components / mitigating_components connect risks to the design tree.
    # Where mitigation text names a physical thing the component is linked; where it
    # does not the field is deliberately empty — linking everything teaches nothing.
    {"id": "RSK00001", "title": "Engine Failure on Takeoff",
     "description": "Loss of engine power during takeoff below 500 ft AGL.  Consequences:"
                    " forced landing straight ahead or within 30° of heading.  Cessna 172's"
                    " low stall speed (48 KIAS clean) and benign stall characteristics"
                    " make survivable outcomes highly probable if the pilot maintains"
                    " airspeed.",
     "severity": "critical", "likelihood": "rare",
     "status": "open", "mitigation": "Pre-takeoff run-up check; engine trend monitoring",
     "linked_requirements": ["PROP0001", "PROP0003"],
     "linked_components": ["ENG"],
     "mitigating_components": ["LMAG", "RMAG"]},
    {"id": "RSK00002", "title": "Fuel Exhaustion in Flight",
     "description": "Fuel mismanagement or undetected leak leading to fuel exhaustion"
                    " before destination.  Leading cause of general aviation accidents"
                    " (approximately 8% of all GA accidents per AOPA Nall Report).",
     "severity": "high", "likelihood": "possible",
     "status": "mitigating", "mitigation": "Fuel totalizer on G1000 MFD; pre-flight dipstick check",
     "linked_requirements": ["PROP0006", "AFRM0006"], "detection": "likely",
     "linked_components": ["TANK", "FQSND"],
     "mitigating_components": ["GDU"]},
    {"id": "RSK00003", "title": "G1000 Display Overheat",
     "description": "PFD or MFD display failure due to excessive cockpit temperatures"
                    " (direct sunlight on ramp, >50°C / 122°F).  The G1000 operating"
                    " temperature specification is −20°C to +55°C.",
     "severity": "medium", "likelihood": "unlikely",
     "status": "monitoring", "mitigation": "Sunshades; cabin ventilation; reversionary mode",
     "linked_requirements": ["AVNC0001", "AVNC0002"], "detection": "obvious",
     "linked_components": ["GDU"]},
    {"id": "RSK00004", "title": "Carbon Monoxide Incapacitation",
     "description": "CO leaking into cabin via exhaust muff cracks, causing progressive"
                    " crew incapacitation (headache → confusion → unconsciousness)."
                    "  CO binds to haemoglobin with 200× the affinity of oxygen.",
     "severity": "critical", "likelihood": "rare",
     # Closed rather than open: the AD retrofit is the mitigation, and a register
     # where nothing ever closes says nothing about how the project is managed.
     "status": "closed", "mitigation": "Active CO detector per AD 2024-01-05; muff inspection",
     "linked_requirements": ["AD2024001", "ENVR0001"], "detection": "possible",
     "linked_components": ["MUFF", "SHUD"],
     "mitigating_components": ["CODT"]},
    {"id": "RSK00005", "title": "Alternator Failure in IMC",
     "description": "Alternator failure while in instrument meteorological conditions (IMC)."
                    "  The essential bus provides 30 min of power — sufficient for an"
                    "  approach at a nearby airport but requiring prompt action.",
     "severity": "high", "likelihood": "unlikely",
     "status": "mitigating", "mitigation": "Essential bus isolation; battery endurance ≥ 30 min",
     "linked_requirements": ["ELEC0001", "ELEC0002", "ELEC0003"], "detection": "undetectable",
     "linked_components": ["ALT"],
     "mitigating_components": ["BATT", "EBUS"]},
    {"id": "RSK00006", "title": "Icing Encounter",
     "description": "Inadvertent encounter with structural icing conditions (visible"
                    " moisture + OAT below freezing).  The Cessna 172S is NOT certified"
                    " for flight into known icing (FIKI).  Ice accumulation on wings"
                    " and tail can increase stall speed by 15-30% and reduce control"
                    " effectiveness.",
     "severity": "high", "likelihood": "possible",
     "status": "open", "mitigation": "Pitot heat; immediate 180° turn or descent",
     "linked_requirements": ["AFRM0004", "ENVR0003", "SAFE0001"],
     "linked_components": ["WING", "EMP"]},
]

# ── comments ──────────────────────────────────────────────────────────────────

COMMENTS = [
    # ── comments on requirements ──────────────────────────────────────────
    {"id": "gen-001", "author": "Chief Systems Engineer",
     "entity_kind": "requirements", "entity_id": "ACFT0000",
     "text": "All FAR Part 23 Amendment 64 references verified against current eCFR text."
            "  Amendment 65 (effective 2025) adds active CO detector mandate — see AD2024001.",
     "resolved": False},
    {"id": "gen-002", "author": "Avionics Lead",
     "entity_kind": "requirements", "entity_id": "AVNC0000",
     "text": "G1000 NXi software baseline is v0582.05.  Confirm with Garmin that this"
            " includes the WAAS/SBAS LPV unlock.  Supplier lead time: 16 weeks.",
     "resolved": False},
    {"id": "gen-003", "author": "Structures Engineer",
     "entity_kind": "requirements", "entity_id": "AFRM0005",
     "text": "Main spar ultimate load FEA complete.  Positive margin of 12% at +3.8g."
            "  Recommend physical load test to validate FEA boundary conditions.",
     "resolved": True},
    {"id": "gen-004", "author": "Electrical Systems",
     "entity_kind": "requirements", "entity_id": "ELEC0002",
     "text": "Battery endurance test at −20°C showed 28 min to essential bus dropout"
            " (vs 30 min spec).  Cold-soak effect reduces SLA capacity by ~15%."
            "  Consider upgrading to 18 Ah battery for cold-weather margin.",
     "resolved": False},
    {"id": "gen-005", "author": "Test Pilot",
     "entity_kind": "requirements", "entity_id": "FLTC0002",
     "text": "Aileron roll rate at Va measured at 42°/s (clean).  This is within the"
            " acceptable range for a training aircraft (40-60°/s).  No adverse yaw"
            " noted during flight test — Frise/differential combination is effective.",
     "resolved": False},
    {"id": "gen-006", "author": "Flight Test",
     "entity_kind": "requirements", "entity_id": "SAFE0001",
     "text": "Stall warning horn calibration verified in flight.  Clean stall: V_S1 = 48 KCAS,"
            " horn at 55 KCAS (7 kn margin).  Full flap: V_S0 = 40 KCAS, horn at 47 KCAS"
            " (7 kn margin).  Both within the 5-10 kn specification.",
     "resolved": False},

    # ── comments on non-requirement entities ──────────────────────────────
    {"id": "gen-007", "author": "Powerplant Lead",
     "entity_kind": "risks", "entity_id": "RSK00001",
     "text": "Engine failure probability modelled at 1.2 × 10⁻⁵ per flight hour"
            " based on Lycoming fleet data.  Well within the FAR 33 continued"
            " airworthiness threshold.  Dual magnetos are the primary mitigation —"
            " single-mag failure is non-catastrophic.",
     "resolved": False},
    {"id": "gen-008", "author": "Avionics Integration",
     "entity_kind": "change_requests", "entity_id": "CR000003",
     "text": "LED lighting retrofit is a good candidate for the first STC batch."
            "  Whelen PARmetheus direct-replacement bulbs have the same base and"
            "  beam pattern as the halogen originals.  Recommend field trial on"
            "  two fleet aircraft before fleet-wide approval.",
     "resolved": False},
    {"id": "gen-009", "author": "Structures Engineer",
     "entity_kind": "components", "entity_id": "SPAR",
     "text": "Main spar forging supplier (Alcoa) has confirmed 16-week lead time"
            " for the 0523001-2 extrusion.  Order must be placed by CDR to avoid"
            " delaying the first structural test article.",
     "resolved": False},
    {"id": "gen-010", "author": "Chief Systems Engineer",
     "entity_kind": "decisions", "entity_id": "DEC0001",
     "text": "The G1000 NXi decision also locks us into the Garmin Connext ecosystem"
            " for future upgrades (GWX 75 weather radar, GFC 700 autopilot)."
            "  This is a strategic advantage — the alternative (G500 TXi) has a"
            " narrower upgrade path.",
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
     "consequences": "Standardises the training fleet on a single avionics platform,"
                    " reducing instructor checkout time and spares inventory.  WAAS/LPV"
                    " capability expands the usable airport set for instrument training"
                    " routes.  Software updates are field-loadable via SD card, eliminating"
                    " LRU removal for updates.  The G1000 NXi also commits the programme"
                    " to the Garmin Connext ecosystem for future upgrades (GWX 75 weather"
                    " radar, GFC 700 autopilot).",
     "linked_requirements": ["AVNC0000", "AVNC0001"],
     "linked_components": ["GDU", "GIA", "GDC", "GRS", "GMU", "GEA", "GTX", "GMA"],
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
     "consequences": "Retains the existing type certificate, avoiding a 12-18 month"
                    " certification programme.  Fuel injection eliminates the carburettor"
                    " ice threat present in the O-360 alternative.  The established supply"
                    " chain and 55,000+ unit service history provide predictable spares"
                    " availability and maintenance procedures.  The IO-390 remains an option"
                    " for a future higher-power variant (Cessna 172S Performance).",
     "linked_requirements": ["PROP0000", "PROP0001", "PROP0002"],
     "linked_components": ["ENG", "FISV", "FDIV", "LMAG", "RMAG"],
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
     "consequences": "Electrical load reduction from 12.0 A to 3.5 A extends alternator"
                    " brush life and reduces battery cycling.  LED lamp life of 10,000+"
                    " hours eliminates the 25-hour halogen bulb replacement interval."
                    "  Owner-performed maintenance classification reduces shop visits."
                    "  The LED PARmetheus direct-replacement bulbs (Whelen) are drop-in"
                    " compatible with the existing mounts and wiring.",
     "linked_requirements": ["SAFE0004", "ELEC0000"],
     "linked_components": ["NAVL", "TAIL", "BCON", "STRB", "TAXI"],
     "status": "accepted", "decided_by": "Electrical Systems"},

    # ── additional decisions ──────────────────────────────────────────────
    {"id": "DEC0004", "title": "Fixed Tricycle Landing Gear",
     "context": "Retractable gear reduces cruise drag but adds weight, complexity,"
               " and failure modes.  The tricycle configuration (nosewheel + two"
               " main wheels) was compared against tailwheel (conventional) gear.",
     "decision": "Retain the fixed tricycle gear configuration.  Retractable gear"
                " was rejected because the weight penalty (~30 kg for the mechanism"
                " and hydraulic system) offsets the cruise speed gain (≈ 8 kt) on a"
                " 120 kt airframe.  Tailwheel was rejected because the 172 is a"
                " primary trainer — tricycle gear is more forgiving on landing.",
     "rationale": "Fixed gear eliminates gear-up landings (the #2 insurance claim on"
                 " retractables), reduces maintenance, and keeps the aircraft insurable"
                 " at flight-school rates.  Spring steel legs absorb landing energy"
                 " without oleo strut maintenance.",
     "consequences": "The fixed gear contributes to the Cessna 172's reputation as"
                    " the safest training aircraft.  Insurance premiums for fixed-gear"
                    " aircraft are typically 40% lower than for retractables.  The"
                    " spring steel main gear design requires only corrosion inspection,"
                    " with no hydraulic service or uplock mechanism to maintain.",
     "linked_requirements": ["LNDG0000", "LNDG0001", "LNDG0002"],
     "linked_components": ["GEAR", "MLEG", "NLEG", "SMDM"],
     "status": "accepted", "decided_by": "Chief Engineer"},
    {"id": "DEC0005", "title": "28 V Electrical System Architecture",
     "context": "Aircraft electrical systems typically use 14 V or 28 V DC.  The"
               " G1000 NXi suite draws ~12 A continuous — roughly 170 W at 14 V vs"
               " the same power at half the current on 28 V.",
     "decision": "Standardise on 28 V DC, negative-ground, single-wire bus.  This"
                " halves current for the same power, reducing wire gauge and weight"
                " by ~3.5 kg across the harness.  The 60 A alternator provides ample"
                " margin even with the full avionics suite and pitot heat.",
     "rationale": "28 V is standard for turbine and advanced piston aircraft, so the"
                 " supply chain is mature.  The weight saving from thinner wiring"
                 " offsets the slight cost premium for 28 V LRUs.  Most avionics OEMs"
                 " (Garmin, BendixKing) ship 28 V as the default variant.",
     "consequences": "Lighter harness saves ~3.5 kg on the empty weight, directly"
                    " increasing useful load.  28 V components have wider availability"
                    " in the certified-aircraft supply chain.  The essential bus concept"
                    " (splitting critical and non-critical loads) became feasible because"
                    " the 60 A alternator provides headroom at 28 V.",
     "linked_requirements": ["ELEC0000", "ELEC0001", "ELEC0003"],
     "linked_components": ["ALT", "BATT", "EBUS", "MBUS"],
     "status": "accepted", "decided_by": "Electrical Systems"},
    {"id": "DEC0006", "title": "Fuel Capacity — 53 US Gallons",
     "context": "Endurance requirement drives tank sizing.  The Cessna 172R carried"
               " 56 US gal (212 L) in integral wing tanks; the 172S reduced this to"
               " 53 US gal (200 L) usable.  A weight/capacity trade was analysed.",
     "decision": "Adopt 53 US gal usable capacity split across two integral wing"
                " tanks, each 26.5 gal (100 L).  The 3-gallon reduction from the"
                " 172R standard was accepted to stay under the 1157 kg MTOW with"
                " the heavier IO-360-L2A engine.",
     "rationale": "53 gal provides ~4.5 hours endurance at 75% power with VFR"
                 " reserves — ample for any realistic training sortie.  The 3-gallon"
                 " reduction vs the 172R saves ~8.5 kg of full-fuel weight,"
                 " preserving 15 kg of payload capacity that would otherwise be lost"
                 " to the heavier fuel-injected engine.",
     "consequences": "Endurance is slightly reduced vs the 172R (4.5 h vs 5.0 h) —"
                    " this is acceptable for the training role where typical sorties"
                    " are 1.0-2.5 h.  The integral (wet-wing) tank construction"
                    " eliminates separate bladder weight.  The 2 × 26.5 gal split"
                    " allows fuel management via the LEFT/RIGHT selector valve.",
     "linked_requirements": ["PROP0006", "AFRM0006"],
     "linked_components": ["TANK", "FQSND", "FUEL", "FSEL"],
     "status": "superseded", "decided_by": "Systems Engineering"},
    {"id": "DEC0007", "title": "McCauley 1A170/E Fixed-Pitch Propeller",
     "context": "A 180 BHP engine can drive either a fixed-pitch or constant-speed"
               " propeller.  Constant-speed props maintain optimal blade angle across"
               " the speed range, improving both climb and cruise performance.",
     "decision": "Retain the McCauley 1A170/E 2-blade fixed-pitch propeller (76 in"
                " diameter, 60 in pitch).  Constant-speed was rejected — it adds"
                " ~15 kg weight, $6K cost, and requires a propeller governor with"
                " its own failure modes (loss of oil pressure → fine pitch → overspeed).",
     "rationale": "Fixed-pitch is simpler, lighter, and cheaper — all priorities for"
                 " a training/rental aircraft.  The 60-inch pitch is a climb-cruise"
                 " compromise that gives acceptable takeoff performance (550 lbf static"
                 " thrust) while cruising at 120 kt at 2400 RPM.",
     "consequences": "The fixed-pitch prop eliminates propeller governor maintenance"
                    " (no oil leaks, no cable rigging).  Takeoff roll is longer than"
                    " a constant-speed equivalent would achieve, but at 960 ft at sea"
                    " level it remains well within the 1500 ft certification limit."
                    "  The prop is owner-serviceable (no special tooling needed).",
     "linked_requirements": ["PROP0005"],
     "linked_components": ["PRPL", "SPIN"],
     "status": "accepted", "decided_by": "Powerplant Lead"},
    {"id": "DEC0008", "title": "High-Wing Configuration",
     "context": "The aircraft configuration (high-wing vs low-wing) fundamentally"
               " determines stability, visibility, cabin access, and maintenance"
               " procedures.  This is the single most defining design choice.",
     "decision": "Retain the high-wing, strut-braced configuration.  A low-wing"
                " alternative was considered but rejected: it would require a"
                " retractable gear (low-wing + fixed gear is aerodynamically"
                " awkward), a different fuel system (no gravity feed), and would"
                " eliminate the downward visibility that instructors value for"
                " ground-reference manoeuvres.",
     "rationale": "The high wing provides inherent roll stability through the"
                 " pendulum effect (CG below the centre of lift), protects the cabin"
                 " from sun and rain on the ramp, and gives the crew exceptional"
                 " downward visibility.  The strut-braced design allows a thinner,"
                 " lighter wing than a cantilever could for the same strength.",
     "consequences": "The high wing defines the Cessna 172's identity.  It enables"
                    " gravity-feed fuel (no electric boost pump needed in cruise),"
                    " simplifies pre-flight inspection (fuel sumps at eye level), and"
                    " provides shade on the ramp — a real comfort benefit at desert"
                    " flight schools.  The strut adds ~4.1 kg per side in drag and"
                    " weight, which is more than offset by the wing mass saving.",
     "linked_requirements": ["AFRM0004"],
     "linked_components": ["WING", "STRT", "SPAR", "ASPAR"],
     "status": "accepted", "decided_by": "Chief Engineer"},
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
        # The four stakeholder groups the requirements already score against.
        # Without these the weighted-value and backlog ranking had nothing to
        # weight: 55 requirements carried priority scores and every one of them
        # came back unranked. Weights are relative, not a distribution — safety
        # outranks the rest on a certified aircraft, and maintenance is a real
        # but secondary voice.
        # The flight phases the requirements below are qualified against. A
        # requirement with no states applies in all of them — a wing spar has
        # no phase — so only genuinely phase-dependent behaviour is tagged.
        "system_states": [
            {"name": "Preflight", "description": "On the ground before engine start: walkaround, checklists, external power available."},
            {"name": "Taxi", "description": "Under own power on the ground, on nosewheel steering and brakes."},
            {"name": "Takeoff", "description": "Full-power roll through the initial climb to 50 ft, flaps at the takeoff setting."},
            {"name": "Climb", "description": "Best-rate or cruise climb to altitude at full throttle."},
            {"name": "Cruise", "description": "Level flight at cruise power with the mixture leaned, navigating en route."},
            {"name": "Descent", "description": "Powered descent from cruise altitude toward the destination."},
            {"name": "Approach", "description": "Configured for landing with flaps extended, on a published or visual approach."},
            {"name": "Landing", "description": "Touchdown through rollout to taxi speed."},
            {"name": "Emergency", "description": "Abnormal or emergency operation: engine failure, fire, or loss of electrical power."},
        ],
        "stakeholders": [
            {"name": "safety", "weight": 3.0},
            {"name": "customers", "weight": 2.0},
            {"name": "development", "weight": 1.5},
            {"name": "maintenance", "weight": 1.0},
        ],
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
        "baselines": [
            {"name": "SRR", "symbol": "S",
             "description": "<p>System Requirements Review — requirements baselined.</p>",
             "due_date": "2026-03-31"},
            {"name": "PDR", "symbol": "P",
             "description": "<p>Preliminary Design Review — architecture agreed.</p>",
             "due_date": "2026-06-30"},
            {"name": "CDR", "symbol": "C",
             "description": "<p>Critical Design Review — design released for build.</p>",
             "due_date": "2026-09-30"},
            {"name": "TRR", "symbol": "T",
             "description": "<p>Test Readiness Review — ready for the flight-test campaign.</p>",
             "due_date": "2026-12-15"},
        ],
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

    # ── System states ──
    # Only requirements whose behaviour actually changes with flight phase are
    # tagged. Structure and architecture requirements are deliberately left
    # empty: "the main spar during cruise" is not a distinction the design
    # makes, and tagging everything would turn the field into noise the moment
    # a reader tried to filter on it.
    _SYSTEM_STATES: dict[str, list[str]] = {
        # Ground handling — only meaningful with weight on wheels.
        "LNDG0001": ["Takeoff", "Landing"],
        "LNDG0002": ["Taxi", "Takeoff", "Landing"],
        "LNDG0003": ["Taxi", "Landing", "Emergency"],
        # Configuration changes are phase-defined by the POH.
        "FLTC0005": ["Takeoff", "Approach", "Landing"],
        "FLTC0006": ["Takeoff", "Approach", "Landing"],
        "FLTC0007": ["Climb", "Cruise", "Descent"],
        # Powerplant — the mag check is a preflight action, mixture is cruise.
        "PROP0002": ["Takeoff", "Climb", "Cruise"],
        "PROP0003": ["Preflight", "Takeoff"],
        "PROP0004": ["Preflight", "Takeoff", "Cruise"],
        "PROP0006": ["Takeoff", "Climb", "Cruise"],
        # Avionics — navigation source depends on the phase of flight.
        "AVNC0004": ["Cruise", "Approach"],
        "AVNC0005": ["Approach"],
        "AVNC0007": ["Preflight", "Taxi", "Approach"],
        "AVNC0008": ["Takeoff", "Cruise", "Approach"],
        # Environmental — heat and defrost are descent/winter concerns.
        "ENVR0001": ["Climb", "Cruise", "Descent"],
        "ENVR0002": ["Taxi", "Cruise"],
        "ENVR0003": ["Descent", "Approach", "Landing"],
        # Electrical.
        "ELEC0002": ["Emergency"],
        "ELEC0004": ["Preflight"],
        # Safety.
        "SAFE0001": ["Takeoff", "Approach", "Landing"],
        "SAFE0003": ["Emergency"],
        "SAFE0004": ["Taxi", "Takeoff", "Landing"],
    }
    for _rid, _states in _SYSTEM_STATES.items():
        reqs[_rid]["system_states"] = list(_states)

    # ── Baseline / status assignment ──
    # Every requirement lands in exactly one of these buckets.  The earliest
    # baseline a requirement is in determines its status (per the contract),
    # and membership is cumulative forward where it makes sense.
    _BASELINE_STATUS: dict[str, tuple[str, list[str]]] = {
        # ── SRR (earliest, most mature) ──
        "ACFT0000":  ("verified",    ["SRR", "PDR", "CDR"]),
        "AFRM0000":  ("verified",    ["SRR", "PDR", "CDR"]),
        "AFRM0004":  ("implemented", ["SRR", "PDR", "CDR"]),
        "AFRM0005":  ("verified",    ["SRR", "PDR"]),
        "PROP0000":  ("implemented", ["SRR", "PDR", "CDR"]),
        "AVNC0000":  ("verified",    ["SRR", "PDR", "CDR"]),
        "FLTC0000":  ("verified",    ["SRR", "PDR", "CDR"]),
        "SAFE0000":  ("implemented", ["SRR", "PDR", "CDR"]),
        "SAFE0001":  ("verified",    ["SRR", "PDR"]),

        # ── PDR-first ──
        "AFRM0001":  ("implemented", ["PDR", "CDR"]),
        "AFRM0003":  ("approved",    ["PDR"]),
        "AFRM0007":  ("approved",    ["PDR", "CDR"]),
        "PROP0001":  ("implemented", ["PDR", "CDR"]),
        "PROP0002":  ("implemented", ["PDR"]),
        "PROP0003":  ("approved",    ["PDR", "CDR"]),
        "AVNC0001":  ("implemented", ["PDR", "CDR"]),
        "AVNC0005":  ("verified",    ["PDR"]),
        "FLTC0001":  ("implemented", ["PDR", "CDR"]),
        "FLTC0002":  ("approved",    ["PDR"]),
        "FLTC0003":  ("approved",    ["PDR"]),

        # ── CDR-first ──
        "AFRM0002":  ("approved",    ["CDR"]),
        "AFRM0006":  ("approved",    ["CDR"]),
        "PROP0005":  ("approved",    ["CDR"]),
        "PROP0006":  ("approved",    ["CDR"]),
        "AVNC0010":  ("approved",    ["CDR"]),
        "AVNC0003":  ("approved",    ["CDR"]),
        "AVNC0006":  ("approved",    ["CDR"]),
        "AVNC0008":  ("approved",    ["CDR"]),
        "FLTC0005":  ("approved",    ["CDR"]),
        "LNDG0000":  ("approved",    ["CDR"]),
        "LNDG0001":  ("approved",    ["CDR"]),
        "LNDG0003":  ("approved",    ["CDR"]),
        "ELEC0000":  ("approved",    ["CDR"]),
        "ELEC0001":  ("approved",    ["CDR"]),
        "ELEC0002":  ("approved",    ["CDR"]),
        "ELEC0003":  ("in_review",   ["CDR"]),
        "ENVR0000":  ("approved",    ["CDR"]),
        "ENVR0001":  ("approved",    ["CDR"]),
        "ENVR0003":  ("approved",    ["CDR"]),
        "SAFE0003":  ("approved",    ["CDR"]),
        "SAFE0004":  ("approved",    ["CDR"]),

        # ── TRR-first ──
        "AVNC0009":  ("in_review",   ["TRR"]),
        "FLTC0006":  ("proposed",    ["TRR"]),
        "FLTC0007":  ("in_review",   ["TRR"]),
        "ELEC0004":  ("proposed",    ["TRR"]),
        "AD2024001": ("proposed",    ["TRR"]),
        "ENVR0002":  ("proposed",    ["TRR"]),

        # ── Unbaselined (proposed) ──
        "AFRM0008":  ("proposed",    []),
        "AFRM0009":  ("proposed",    []),
        "PROP0004":  ("proposed",    []),
        "AVNC0002":  ("proposed",    []),
        "AVNC0004":  ("proposed",    []),
        "FLTC0004":  ("proposed",    []),
        # ENVR0002 moved to TRR below
        "LNDG0002":  ("proposed",    []),
        "OVERVIEW":  ("proposed",    []),

        # ── Special: exactly one rejected, one deprecated ──
        "SAFE0002":  ("rejected",    []),
        "AVNC0007":  ("deprecated",  []),
    }

    for rid, (status, baselines) in _BASELINE_STATUS.items():
        reqs[rid]["status"] = status
        reqs[rid]["baselines"] = list(baselines)

    vcs = {}
    for vc in VERIFICATION_CASES:
        vcs[vc["id"]] = {
            **vc,
            "status": vc.get("status", "pending"),
            "result": vc.get("result"),
            "verified_requirements": [],
        }

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

    # Additional realistic engineering attributes (§7)
    _add_attr(reqs["ELEC0000"], "bus_voltage", "28 VDC")
    _add_attr(reqs["ELEC0000"], "ground_clearance", "0")
    _add_attr(reqs["PROP0001"], "supplier_pn", "IO-360-L2A")
    _add_attr(reqs["PROP0001"], "tbo_hours", "2000")
    _add_attr(reqs["AVNC0000"], "icd_ref", "ICD-G1000-172-001")
    _add_attr(reqs["AVNC0000"], "software_baseline", "v0582.05")
    _add_attr(reqs["AFRM0004"], "airfoil", "NACA 2412")
    _add_attr(reqs["LNDG0000"], "design_sink_rate", "10 fps")

    # ── Reviewed fingerprints (§5) ──
    # Compute fingerprints *after* relations are attached so the fingerprint
    # matches what the API will recompute on read.
    from app.services.fingerprint import compute_fingerprint

    _SRR_PDR_IDS = {rid for rid, (_, bl) in _BASELINE_STATUS.items()
                    if any(b in ("SRR", "PDR") for b in bl)}
    for rid in _SRR_PDR_IDS:
        reqs[rid]["reviewed"] = compute_fingerprint(reqs[rid])

    # ── Parametrics: SysML-style computable requirements ─────────────────
    # Weight & balance: MTOW bound, useful load derived across requirements,
    # and the C172S's real full-fuel payload shortfall as a live failure.
    reqs["ACFT0000"]["parameters"] = [
        {"name": "mtow", "value": 1157, "unit": "kg", "expr": None},
        {"name": "useful_load", "value": None, "unit": "kg",
         "expr": "mtow - AFRM0000.empty_mass"},
        {"name": "full_fuel_payload", "value": None, "unit": "kg",
         "expr": "useful_load - PROP0006.fuel_mass"},
    ]
    reqs["ACFT0000"]["constraints"] = [
        {"expr": "useful_load >= 380", "assume": None},
        # 390 kg useful load minus ~145 kg of full fuel leaves ~245 kg — this
        # fails on purpose: full tanks and four adults never fit in a 172S.
        {"expr": "full_fuel_payload >= 250", "assume": None},
    ]
    reqs["AFRM0000"]["parameters"] = [
        {"name": "empty_mass", "value": 767, "unit": "kg", "expr": None},
        {"name": "design_mass", "value": None, "unit": "kg",
         "expr": "rollup('C172', 'mass')"},
    ]
    reqs["AFRM0000"]["subject"] = "C172"
    reqs["AFRM0000"]["constraints"] = [
        {"expr": "empty_mass <= 780", "assume": None},
        # Budget rollup via a reusable MassBudget definition: everything tracked
        # in the design tree must fit inside the empty weight.
        {"constraint_def": "MassBudget",
         "bindings": {"actual": "AFRM0000.design_mass", "limit": "AFRM0000.empty_mass"}},
    ]

    # Structure: bound plus measured evidence from the static test.
    reqs["AFRM0005"]["parameters"] = [
        {"name": "ultimate_load_factor", "value": 5.89, "unit": "g", "expr": None}]
    reqs["AFRM0005"]["constraints"] = [
        {"expr": "ultimate_load_factor >= 5.7", "assume": None}]
    vcs["VCAF0001"]["measurements"] = [
        {"parameter": "AFRM0005.ultimate_load_factor", "value": 5.92, "unit": "g"}]

    # Fuel: derived fuel mass and endurance, measured max flow, and a
    # cross-requirement capacity check from the wing tanks.
    reqs["PROP0006"]["parameters"] = [
        {"name": "usable_fuel_l", "value": 201, "unit": "L", "expr": None},
        {"name": "fuel_density", "value": 0.72, "unit": "kg/L", "expr": None},
        {"name": "cruise_burn_lph", "value": 36, "unit": "L/h", "expr": None},
        {"name": "fuel_mass", "value": None, "unit": "kg",
         "expr": "usable_fuel_l * fuel_density"},
        {"name": "endurance", "value": None, "unit": "h",
         "expr": "usable_fuel_l / cruise_burn_lph"},
        {"name": "max_flow_gph", "value": 15.0, "unit": "GPH", "expr": None},
    ]
    reqs["PROP0006"]["constraints"] = [
        {"expr": "endurance >= 4.5", "assume": None},
        {"expr": "max_flow_gph >= 14", "assume": None},
    ]
    vcs["VCFL0001"]["measurements"] = [
        {"parameter": "PROP0006.max_flow_gph", "value": 15.4, "unit": "GPH"}]
    reqs["AFRM0006"]["parameters"] = [
        {"name": "tank_capacity_l", "value": 106, "unit": "L", "expr": None}]
    reqs["AFRM0006"]["constraints"] = [
        {"expr": "2 * tank_capacity_l >= PROP0006.usable_fuel_l", "assume": None}]

    # Engine: a chained comparison bound with measured run-up evidence.
    reqs["PROP0001"]["parameters"] = [
        {"name": "rated_power_hp", "value": 180, "unit": "hp", "expr": None},
        {"name": "static_rpm", "value": 2360, "unit": "RPM", "expr": None},
    ]
    reqs["PROP0001"]["constraints"] = [
        {"expr": "rated_power_hp >= 160", "assume": None},
        {"expr": "2300 <= static_rpm <= 2400", "assume": None},
    ]
    vcs["VCPR0001"]["measurements"] = [
        {"parameter": "PROP0001.static_rpm", "value": 2345, "unit": "RPM"}]

    # Electrical: the 80 %-continuous-load rule fed by a current rollup over
    # the avionics subtree.
    reqs["ELEC0001"]["parameters"] = [
        {"name": "alternator_amps", "value": 60, "unit": "A", "expr": None},
        {"name": "continuous_load_limit", "value": None, "unit": "A",
         "expr": "0.8 * alternator_amps"},
    ]
    reqs["ELEC0001"]["constraints"] = [
        {"expr": "rollup('AVIO', 'current') <= continuous_load_limit",
         "assume": None}]

    # Stall warning: the horn must sound 5-10 kn above stall; flight test
    # measured where it actually sounds.
    reqs["SAFE0001"]["parameters"] = [
        {"name": "stall_speed_kcas", "value": 48, "unit": "kn", "expr": None},
        {"name": "horn_activation_kn", "value": 54, "unit": "kn", "expr": None},
    ]
    reqs["SAFE0001"]["constraints"] = [
        {"expr": "stall_speed_kcas + 5 <= horn_activation_kn <= stall_speed_kcas + 10",
         "assume": None}]
    vcs["VCSF0001"]["measurements"] = [
        {"parameter": "SAFE0001.horn_activation_kn", "value": 55, "unit": "kn"}]

    # Cabin heat: an assume/require pair — the arctic clause is out of scope
    # at the -18 °C design case, the standard clause applies and passes.
    reqs["ENVR0001"]["parameters"] = [
        {"name": "oat_c", "value": -18, "unit": "degC", "expr": None},
        {"name": "temp_rise_c", "value": 25, "unit": "degC", "expr": None},
    ]
    reqs["ENVR0001"]["constraints"] = [
        {"expr": "temp_rise_c >= 22", "assume": None},
        {"expr": "temp_rise_c >= 30", "assume": "oat_c <= -30"},
    ]

    # ELT battery life is still TBD from the vendor — an honest "unknown".
    reqs["SAFE0003"]["parameters"] = [
        {"name": "battery_life_h", "value": None, "unit": "h", "expr": None}]
    reqs["SAFE0003"]["constraints"] = [
        {"expr": "battery_life_h >= 24", "assume": None}]

    # ── Expanded parametrics: more subsystem budget rollups and cross-req chains ──

    # Landing gear: max taxi mass bound and brake energy
    reqs["LNDG0000"]["parameters"] = [
        {"name": "design_mass", "value": None, "unit": "kg",
         "expr": "rollup('GEAR', 'mass')"},
        {"name": "max_load_kg", "value": 1220, "unit": "kg", "expr": None},
    ]
    reqs["LNDG0000"]["constraints"] = [
        {"expr": "max_load_kg >= ACFT0000.mtow", "assume": None},
        # The gear mass budget: assembled weight must fit within 65 kg
        {"expr": "design_mass <= 65", "assume": None},
    ]
    reqs["LNDG0000"]["subject"] = "C172"

    # Propeller: torque margin and balance
    reqs["PROP0005"]["parameters"] = [
        {"name": "rated_rpm", "value": 2700, "unit": "RPM", "expr": None},
        {"name": "max_torque_nm", "value": 280, "unit": "N·m", "expr": None},
        {"name": "operating_torque", "value": None, "unit": "N·m",
         "expr": "PROP0001.rated_power_hp * 7124 / rated_rpm"},
    ]
    reqs["PROP0005"]["constraints"] = [
        {"expr": "operating_torque <= max_torque_nm", "assume": None},
    ]
    vcs["VCPR0003"]["measurements"] = [
        {"parameter": "PROP0005.operating_torque", "value": 474, "unit": "N·m"}]

    # Fuel injection: flow balance measured by calibration test
    reqs["PROP0002"]["parameters"] = [
        {"name": "max_flow_imbalance_gph", "value": 0.5, "unit": "GPH", "expr": None},
    ]
    reqs["PROP0002"]["constraints"] = [
        {"expr": "max_flow_imbalance_gph <= 0.5", "assume": None},
    ]
    vcs["VCPR0004"]["measurements"] = [
        {"parameter": "PROP0002.max_flow_imbalance_gph", "value": 0.3, "unit": "GPH"}]

    # Magneto: RPM drop at run-up
    reqs["PROP0003"]["parameters"] = [
        {"name": "magneto_drop_rpm", "value": 125, "unit": "RPM", "expr": None},
    ]
    reqs["PROP0003"]["constraints"] = [
        {"expr": "magneto_drop_rpm <= 150", "assume": None},
    ]

    # Fuselage: structural load from component rollup
    reqs["AFRM0001"]["parameters"] = [
        {"name": "fuselage_mass", "value": None, "unit": "kg",
         "expr": "rollup('FUSE', 'mass')"},
        {"name": "max_fuselage_mass", "value": 310, "unit": "kg", "expr": None},
    ]
    reqs["AFRM0001"]["constraints"] = [
        {"expr": "fuselage_mass <= max_fuselage_mass", "assume": None},
    ]
    reqs["AFRM0001"]["subject"] = "C172"

    # Flaps: deployment time
    reqs["FLTC0006"]["parameters"] = [
        {"name": "deploy_time_s", "value": 4.2, "unit": "s", "expr": None},
    ]
    reqs["FLTC0006"]["constraints"] = [
        {"expr": "deploy_time_s <= 5", "assume": None},
    ]

    # Brakes: energy absorption for rejected takeoff
    reqs["LNDG0003"]["parameters"] = [
        {"name": "ke_absorption_mj", "value": 3.8, "unit": "MJ", "expr": None},
        {"name": "rejected_takeoff_ke", "value": None, "unit": "MJ",
         "expr": "0.5 * ACFT0000.mtow * (50 / 3.6) ** 2 / 1000000"},
    ]
    reqs["LNDG0003"]["constraints"] = [
        {"expr": "ke_absorption_mj >= rejected_takeoff_ke", "assume": None},
    ]

    # Avionics: total current budget from rollup
    reqs["AVNC0000"]["parameters"] = [
        {"name": "total_current_a", "value": None, "unit": "A",
         "expr": "rollup('AVIO', 'current')"},
        {"name": "max_current_a", "value": 25, "unit": "A", "expr": None},
    ]
    reqs["AVNC0000"]["constraints"] = [
        {"expr": "total_current_a <= max_current_a", "assume": None},
    ]
    reqs["AVNC0000"]["subject"] = "C172"

    # Navigation: GPS outage endurance (cross-req chain with fuel)
    reqs["AVNC0004"]["parameters"] = [
        {"name": "waas_accuracy_m", "value": 3.5, "unit": "m", "expr": None},
    ]
    reqs["AVNC0004"]["constraints"] = [
        {"expr": "waas_accuracy_m <= 5", "assume": None},
        {"expr": "PROP0006.endurance >= 4", "assume": None},
    ]

    # COM range: measured transmit power
    reqs["AVNC0007"]["parameters"] = [
        {"name": "tx_power_w", "value": 16, "unit": "W", "expr": None},
    ]
    reqs["AVNC0007"]["constraints"] = [
        {"expr": "tx_power_w >= 10", "assume": None},
    ]
    vcs["VCAV0003"]["measurements"] = [
        {"parameter": "AVNC0007.tx_power_w", "value": 16.5, "unit": "W"}]

    # Total electrical budget: sum all current draws
    reqs["ELEC0000"]["parameters"] = [
        {"name": "total_current_a", "value": None, "unit": "A",
         "expr": "rollup('C172', 'current')"},
        {"name": "alternator_limit", "value": None, "unit": "A",
         "expr": "ELEC0001.alternator_amps"},
    ]
    reqs["ELEC0000"]["constraints"] = [
        {"expr": "total_current_a <= alternator_limit", "assume": None},
    ]
    reqs["ELEC0000"]["subject"] = "C172"

    # Flight controls: aileron deflection range
    reqs["FLTC0002"]["parameters"] = [
        {"name": "up_deflection_deg", "value": 20, "unit": "deg", "expr": None},
        {"name": "down_deflection_deg", "value": 15, "unit": "deg", "expr": None},
    ]
    reqs["FLTC0002"]["constraints"] = [
        {"expr": "up_deflection_deg >= 18", "assume": None},
        {"expr": "down_deflection_deg >= 12", "assume": None},
    ]

    # Elevator control surface range
    reqs["FLTC0003"]["parameters"] = [
        {"name": "up_deflection_deg", "value": 25, "unit": "deg", "expr": None},
        {"name": "down_deflection_deg", "value": 15, "unit": "deg", "expr": None},
    ]
    reqs["FLTC0003"]["constraints"] = [
        {"expr": "up_deflection_deg >= 22", "assume": None},
        {"expr": "down_deflection_deg >= 13", "assume": None},
    ]

    # Rudder control range
    reqs["FLTC0004"]["parameters"] = [
        {"name": "deflection_deg", "value": 27, "unit": "deg", "expr": None},
    ]
    reqs["FLTC0004"]["constraints"] = [
        {"expr": "deflection_deg >= 24", "assume": None},
    ]

    # Fire detection: temperature thresholds
    reqs["SAFE0002"]["parameters"] = [
        {"name": "alarm_temp_c", "value": 175, "unit": "degC", "expr": None},
        {"name": "normal_max_c", "value": 120, "unit": "degC", "expr": None},
    ]
    reqs["SAFE0002"]["constraints"] = [
        {"expr": "150 <= alarm_temp_c <= 200", "assume": None},
        {"expr": "alarm_temp_c >= normal_max_c + 30", "assume": None},
    ]

    # Nose gear: max steering angle
    reqs["LNDG0002"]["parameters"] = [
        {"name": "steer_angle_deg", "value": 12, "unit": "deg", "expr": None},
    ]
    reqs["LNDG0002"]["constraints"] = [
        {"expr": "steer_angle_deg >= 10", "assume": None},
    ]

    # Cabin heat: measured temperature rise from test
    vcs["VCEN0001"]["measurements"] = [
        {"parameter": "ENVR0001.temp_rise_c", "value": 26, "unit": "degC"}]

    # `allocated_to` is derived from component.satisfies (the allocation
    # matrix maintains both). The hand-written values here predated that and
    # named owning *teams* ("Airframe Team", "Structures") rather than the
    # components that satisfy the requirement, so the seeded project shipped
    # 54 of 57 requirements whose allocation disagreed with its own allocation
    # matrix. Derive it instead, so the demo shows the field meaning what the
    # UI now says it means.
    _owners: dict[str, list[str]] = {}
    for comp in COMPONENTS:
        for req_id in (comp.get("satisfies") or []):
            _owners.setdefault(req_id, []).append(comp.get("name") or comp["id"])
    for r in reqs.values():
        r["allocated_to"] = ", ".join(sorted(_owners.get(r["id"], [])))

    # ── Frozen baselines (§6) ──
    # Freeze SRR and PDR so the baseline diff view has something to show.
    # CDR and TRR stay unfrozen — a project where the future is frozen makes no sense.

    def _freeze_baseline(name: str, symbol: str, description: str,
                         frozen_at: str, status_overrides: dict[str, str] | None = None):
        snapshot = {}
        for rid, r in reqs.items():
            snap = {
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "status": r.get("status", "proposed"),
                "priority": r.get("priority", "medium"),
                "type": r.get("type", "functional"),
                "parent": r.get("parent"),
                "relations": r.get("relations", []),
                "verification_cases": r.get("verification_cases", []),
                "rationale": r.get("rationale", ""),
                "source": r.get("source", ""),
                "allocated_to": r.get("allocated_to", ""),
            }
            if status_overrides and rid in status_overrides:
                snap["status"] = status_overrides[rid]
            snapshot[rid] = snap
        store.write_item("baselines", name, {
            "id": name, "name": name, "symbol": symbol, "description": description,
            "frozen": True, "frozen_at": frozen_at, "snapshot": snapshot,
        })

    _freeze_baseline("SRR", "S",
                     "<p>System Requirements Review — requirements baselined.</p>",
                     "2026-03-31T10:00:00+00:00",
                     status_overrides={
                         # Two verified → snapshot as approved
                         "ACFT0000": "approved",
                         "AVNC0000": "approved",
                         # Two implemented (lowest ids) → snapshot as approved
                         "AFRM0004": "approved",
                         "PROP0000": "approved",
                     })
    _freeze_baseline("PDR", "P",
                     "<p>Preliminary Design Review — architecture agreed.</p>",
                     "2026-06-30T14:00:00+00:00")

    # ── Component baselines (§8) ──
    # Tick components into the same baseline definitions the requirements use,
    # respecting what would plausibly have existed at each review gate.
    _COMP_BASELINES: dict[str, list[str]] = {
        # ── SRR — only the top-level system concept existed ──
        "C172":  ["SRR", "PDR", "CDR"],

        # ── PDR — major assemblies and subsystems defined by Preliminary Design Review ──
        "FUSE":  ["PDR", "CDR"],
        "WING":  ["PDR", "CDR"],
        "EMP":   ["PDR", "CDR"],
        "GEAR":  ["PDR", "CDR"],
        "ENG":   ["PDR", "CDR"],
        "PRPL":  ["PDR", "CDR"],
        "FUEL":  ["PDR", "CDR"],
        "AVIO":  ["PDR", "CDR"],
        "ELEC":  ["PDR", "CDR"],
        "FLTC":  ["PDR", "CDR"],
        "ENVR":  ["PDR", "CDR"],
        "SAFE":  ["PDR", "CDR"],

        # ── CDR — detailed parts designed and released for build ──
        "COCK":  ["CDR"],
        "IPAN":  ["CDR"],
        "YOKE":  ["CDR"],
        "PEDL":  ["CDR"],
        "SEAT":  ["CDR"],
        "RSEAT": ["CDR"],
        "HARN":  ["CDR"],
        "DOOR":  ["CDR"],
        "SPAR":  ["CDR", "TRR"],
        "ASPAR": ["CDR"],
        "TANK":  ["CDR", "TRR"],
        "FQSND": ["CDR"],
        "STRT":  ["CDR"],
        "HSTB":  ["CDR"],
        "ELEV":  ["CDR", "TRR"],
        "VFIN":  ["CDR"],
        "RUDD":  ["CDR", "TRR"],
        "MLEG":  ["CDR"],
        "MWHE":  ["CDR"],
        "BRAK":  ["CDR"],
        "NLEG":  ["CDR"],
        "SMDM":  ["CDR"],
        "EMNT":  ["CDR"],
        "FISV":  ["CDR"],
        "FDIV":  ["CDR"],
        "LMAG":  ["CDR"],
        "RMAG":  ["CDR"],
        "MUFF":  ["CDR"],
        "OILS":  ["CDR"],
        "SPIN":  ["CDR"],
        "FSEL":  ["CDR"],
        "BPMP":  ["CDR"],
        "EPMP":  ["CDR"],
        "GCOL":  ["CDR"],
        "GDU":   ["CDR", "TRR"],
        "GIA":   ["CDR", "TRR"],
        "GDC":   ["CDR"],
        "GRS":   ["CDR"],
        "GMU":   ["CDR"],
        "GEA":   ["CDR"],
        "GTX":   ["CDR", "TRR"],
        "GMA":   ["CDR"],
        "ALT":   ["CDR"],
        "VREG":  ["CDR"],
        "BATT":  ["CDR"],
        "MBUS":  ["CDR"],
        "EBUS":  ["CDR"],
        "EPOW":  ["CDR"],
        "AILR":  ["CDR", "TRR"],
        "ELVC":  ["CDR", "TRR"],
        "FLAP":  ["CDR"],
        "FLAPM": ["CDR"],
        "TRIM":  ["CDR"],
        "TRSV":  ["CDR"],
        "SHUD":  ["CDR"],
        "BVAL":  ["CDR"],
        "DFRS":  ["CDR"],
        "AVNT":  ["CDR"],
        "SWRN":  ["CDR"],
        "FDTC":  ["CDR"],
        "ELT":   ["CDR"],
        "NAVL":  ["CDR"],
        "TAIL":  ["CDR"],
        "BCON":  ["CDR"],
        "STRB":  ["CDR"],
        "TAXI":  ["CDR"],
        "CODT":  ["CDR"],
    }

    _comp_with_baselines = []
    for comp in COMPONENTS:
        comp = dict(comp)
        cid = comp["id"]
        if cid in _COMP_BASELINES:
            comp["baselines"] = list(_COMP_BASELINES[cid])
        _comp_with_baselines.append(comp)

    # Write everything to disk
    for r in reqs.values():
        store.create_requirement(r)
    for vc in vcs.values():
        store.create_verification_case(vc)
    for comp in _comp_with_baselines:
        store.create_component(comp)
    for spec in SPECIFICATIONS:
        store.create_specification(dict(spec))

    store.write_traces({"links": TRACES})

    for cr_data in CHANGE_REQUESTS:
        store.create_item("change_requests", {
            **{k: v for k, v in cr_data.items() if k not in ("status", "submitted_by",
                                                              "affected_components")},
            "status": cr_data.get("status", "submitted"),
            "submitted_by": cr_data.get("submitted_by", ""),
            "reviewed_by": "",
            "approved_by": "",
            "affected_components": list(cr_data.get("affected_components", [])),
        })

    for risk in RISKS:
        store.create_item("risks", {
            **{k: v for k, v in risk.items()
               if k not in ("status", "mitigation", "linked_requirements",
                            "linked_components", "mitigating_components")},
            "impact": "",
            "status": risk.get("status", "open"),
            "mitigation": risk.get("mitigation", ""),
            # Was hardcoded to [], which silently discarded whatever the register
            # declared — so every risk in the demo looked untraced.
            "linked_requirements": list(risk.get("linked_requirements", [])),
            "linked_components": list(risk.get("linked_components", [])),
            "mitigating_components": list(risk.get("mitigating_components", [])),
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

    # Reusable SysML v2-style parametric definitions.
    store.write_item("definitions", "MassBudget", {
        "id": "MassBudget", "type": "constraint",
        "name": "Mass budget", "parameters": ["actual", "limit"],
        "expr": "actual <= limit", "unit": "",
        "doc": "A rolled-up mass must fit within its allocated limit.",
    })
    store.write_item("definitions", "PowerMargin", {
        "id": "PowerMargin", "type": "calc",
        "name": "Continuous power margin", "parameters": ["draw", "capacity"],
        "expr": "capacity - draw", "unit": "A",
        "doc": "Headroom between a load draw and its supply capacity.",
    })
    store.write_item("definitions", "TorqueMargin", {
        "id": "TorqueMargin", "type": "calc",
        "name": "Torque margin", "parameters": ["max", "actual"],
        "expr": "max - actual", "unit": "N·m",
        "doc": "Safety margin between maximum rated torque and operating torque.",
    })
    store.write_item("definitions", "TempEnvelope", {
        "id": "TempEnvelope", "type": "constraint",
        "name": "Temperature operating envelope",
        "parameters": ["min_temp", "actual", "max_temp"],
        "expr": "min_temp <= actual and actual <= max_temp", "unit": "",
        "doc": "Verify a measured value falls within a specified temperature range.",
    })
    store.write_item("definitions", "SpeedMargin", {
        "id": "SpeedMargin", "type": "calc",
        "name": "Speed margin above stall", "parameters": ["actual", "stall"],
        "expr": "actual - stall", "unit": "kn",
        "doc": "Compute knot margin above stall speed for safety analysis.",
    })

    # A what-if analysis case: does the empty-weight budget still hold if the
    # avionics upgrade adds 12 kg? Scoped to the mass-budget requirement.
    store.write_item("analysis_cases", "avionics-upgrade", {
        "id": "avionics-upgrade", "name": "Avionics upgrade (+12 kg)",
        "doc": "Explore the empty-weight budget with a heavier avionics fit.",
        "scope": ["AFRM0000"],
        "scope_components": ["AVIO"],
        "overrides": {"AFRM0000.empty_mass": 779},
    })
    store.write_item("analysis_cases", "cold-weather-ops", {
        "id": "cold-weather-ops", "name": "Cold weather operations (-35 °C)",
        "doc": "Verify cabin heat meets the arctic clause when OAT drops below design point.",
        "scope": ["ENVR0001"],
        "scope_components": ["SHUD", "ENVR"],
        "overrides": {"ENVR0001.oat_c": -35},
    })
    store.write_item("analysis_cases", "heavy-config", {
        "id": "heavy-config", "name": "Heavy configuration (793 kg empty)",
        "doc": "Test mass budget when extra equipment pushes empty mass near the 780 kg limit.",
        "scope": ["AFRM0000", "ACFT0000"],
        "scope_components": ["C172"],
        "overrides": {"AFRM0000.empty_mass": 793},
    })
    store.write_item("analysis_cases", "high-power-avionics", {
        "id": "high-power-avionics", "name": "High-power avionics fit",
        "doc": "Check electrical budget if avionics total draw increases to 22 A.",
        "scope": ["ELEC0001", "AVNC0000"],
        "scope_components": ["AVIO", "ALT"],
        "overrides": {"AVNC0000.max_current_a": 22},
    })
    store.write_item("analysis_cases", "reduced-power-engine", {
        "id": "reduced-power-engine", "name": "Reduced-power engine (160 hp)",
        "doc": "Impact on propeller torque margin if engine is de-rated to minimum spec.",
        "scope": ["PROP0001", "PROP0005"],
        "scope_components": ["ENG", "PRPL"],
        "overrides": {"PROP0001.rated_power_hp": 160},
    })

    return True
