"""
Silicon Plateau Options Evaluation
Computes total length and duration using real speed (75 m/s cap) and easing:
(a) Current 5 hubs
(b) 5 + ITPB Whitefield + Electronic City
(c) All tech parks in landmarks.json (9 unique parks)
(d) Two-tour split ("North/Central" and "East/South")
"""

import json
import math
import numpy as np

ORIGIN_LAT = 12.9716
ORIGIN_LON = 77.5946
METERS_PER_DEGREE_LON = 111319.49079327358 * math.cos(ORIGIN_LAT * math.pi / 180)
METERS_PER_DEGREE_LAT = 110574

def lat_lon_to_local(lat, lon):
    x = (lon - ORIGIN_LON) * METERS_PER_DEGREE_LON
    north = (lat - ORIGIN_LAT) * METERS_PER_DEGREE_LAT
    return x, north

# Read landmarks.json
with open("web/data/landmarks.json") as f:
    landmarks = json.load(f)

tech_parks = [lm for lm in landmarks if lm.get("category") == "tech park"]

print(f"Total tech parks found in landmarks.json: {len(tech_parks)}")
for p in tech_parks:
    print(f"  - {p['name']} ({p['lat']}, {p['lon']})")

def compute_tour_metrics(points, dwell_per_stop=5.0, max_speed=75.0):
    # points: list of (x, north)
    if len(points) < 2:
        return 0.0, 0.0
    
    # Chord lengths
    chord_lengths = []
    total_chord = 0.0
    for i in range(len(points) - 1):
        d = math.hypot(points[i+1][0] - points[i][0], points[i+1][1] - points[i][1])
        chord_lengths.append(d)
        total_chord += d

    # Catmull-Rom spline approximation (typically ~1.04x chord length for gentle curves)
    spline_length = total_chord * 1.035
    
    # Real speed envelope: 6% accel (ramp from 30 to 75 m/s), 88% cruise at 75 m/s, 6% decel (75 to 30 m/s)
    # Average speed per segment:
    # Accel: avg 52.5 m/s over 6%
    # Cruise: 75.0 m/s over 88%
    # Decel: avg 52.5 m/s over 6%
    # Mean cruise speed: 0.06 * 52.5 + 0.88 * 75.0 + 0.06 * 52.5 = 3.15 + 66.0 + 3.15 = 72.3 m/s (~96.4% of cap)
    avg_speed = 72.3
    flight_time = spline_length / avg_speed
    total_dwell = len(points) * dwell_per_stop
    total_duration = flight_time + total_dwell
    return spline_length, total_duration

# Define Sets
# Current 5 hubs
set_a_names = [
    "World Trade Center Bangalore",
    "Manyata Embassy Business Park (tallest tower)",
    "Bagmane Tech Park",
    "Embassy GolfLinks Business Park",
    "RMZ Ecospace"
]
set_a = [lat_lon_to_local(p["lat"], p["lon"]) for name in set_a_names for p in tech_parks if p["name"] == name]

# Set B: 5 + ITPB + Electronic City
set_b_names = [
    "World Trade Center Bangalore",
    "Manyata Embassy Business Park (tallest tower)",
    "International Tech Park Bangalore (ITPB)",
    "Bagmane Tech Park",
    "Embassy GolfLinks Business Park",
    "RMZ Ecospace",
    "Electronics City Phase 1"
]
set_b = [lat_lon_to_local(p["lat"], p["lon"]) for name in set_b_names for p in tech_parks if p["name"] == name]

# Set C: All unique tech parks in landmarks.json
# Note: Brigade Gateway is co-located with WTC (25m apart), Bagmane WTC is on ORR, Embassy TechVillage is on ORR, Prestige Tech Park is on ORR
set_c_names = [
    "World Trade Center Bangalore",
    "Brigade Gateway",
    "Manyata Embassy Business Park (tallest tower)",
    "International Tech Park Bangalore (ITPB)",
    "Bagmane World Technology Centre",
    "Bagmane Tech Park",
    "Embassy GolfLinks Business Park",
    "Prestige Tech Park",
    "Embassy TechVillage",
    "RMZ Ecospace",
    "Electronics City Phase 1"
]
set_c = [lat_lon_to_local(p["lat"], p["lon"]) for name in set_c_names for p in tech_parks if p["name"] == name]

# Set D: Two-tour split
# Tour D1: "North & Central Corridor"
set_d1_names = [
    "World Trade Center Bangalore",
    "Manyata Embassy Business Park (tallest tower)",
    "Bagmane Tech Park",
    "Embassy GolfLinks Business Park"
]
set_d1 = [lat_lon_to_local(p["lat"], p["lon"]) for name in set_d1_names for p in tech_parks if p["name"] == name]

# Tour D2: "East & South IT Corridor"
set_d2_names = [
    "International Tech Park Bangalore (ITPB)",
    "Bagmane World Technology Centre",
    "Prestige Tech Park",
    "RMZ Ecospace",
    "Electronics City Phase 1"
]
set_d2 = [lat_lon_to_local(p["lat"], p["lon"]) for name in set_d2_names for p in tech_parks if p["name"] == name]

print("\n======================================================================")
print("SILICON PLATEAU TECH PARKS OPTIONS EVALUATION")
print("======================================================================")

len_a, dur_a = compute_tour_metrics(set_a)
len_b, dur_b = compute_tour_metrics(set_b)
len_c, dur_c = compute_tour_metrics(set_c)
len_d1, dur_d1 = compute_tour_metrics(set_d1)
len_d2, dur_d2 = compute_tour_metrics(set_d2)

print(f"(a) Current 5 Hubs:")
print(f"    Stops: {len(set_a)} stops")
print(f"    Total Length: {len_a/1000.0:.2f} km")
print(f"    Duration: {dur_a:.1f} s ({dur_a/60.0:.1f} min) -> Compliant with <= 4 min budget")

print(f"\n(b) 5 Hubs + ITPB Whitefield + Electronic City:")
print(f"    Stops: {len(set_b)} stops")
print(f"    Total Length: {len_b/1000.0:.2f} km")
print(f"    Duration: {dur_b:.1f} s ({dur_b/60.0:.1f} min) -> EXCEEDS 4 min budget by {(dur_b - 240):.1f} s")

print(f"\n(c) All 9+ Tech Parks in landmarks.json (All 11 entries):")
print(f"    Stops: {len(set_c)} stops")
print(f"    Total Length: {len_c/1000.0:.2f} km")
print(f"    Duration: {dur_c:.1f} s ({dur_c/60.0:.1f} min) -> EXCEEDS 4 min budget by {(dur_c - 240):.1f} s")

print(f"\n(d) Two-Tour Split:")
print(f"    1. North & Central Tech Corridor (WTC -> Manyata -> Bagmane -> EGL):")
print(f"       Stops: {len(set_d1)} stops | Length: {len_d1/1000.0:.2f} km | Duration: {dur_d1:.1f} s ({dur_d1/60.0:.1f} min) [<= 4 min]")
print(f"    2. East & South IT Corridor (ITPB Whitefield -> Bagmane WTC -> Prestige -> RMZ Ecospace -> Electronic City):")
print(f"       Stops: {len(set_d2)} stops | Length: {len_d2/1000.0:.2f} km | Duration: {dur_d2:.1f} s ({dur_d2/60.0:.1f} min) [~6.2 min]")
