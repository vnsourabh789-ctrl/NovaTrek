"""Render a saved trip as portable Markdown."""

from __future__ import annotations

from datetime import datetime


def trip_to_markdown(trip: dict) -> str:
    i, b = trip["intent"], trip["budget"]
    it = trip["itinerary"]
    out = [f"# {trip['title']}", ""]
    created = datetime.fromtimestamp(trip["created_at"]).strftime("%Y-%m-%d")
    out.append(f"*NovaTrek mission · {created} · {i['travelers']} traveller(s) · {i['budget']} tier*")
    out += ["", it.get("summary", ""), ""]

    f = trip.get("flights") or {}
    out.append("## Flights")
    if f.get("available"):
        oa, da = f.get("origin_airport"), f.get("dest_airport")
        route = f"{oa['iata']} → {da['iata']}" if oa and da else f"{i.get('origin')} → {i['destination']}"
        out.append(f"- Route: {route} · {f['distance_km']:,} km · ~{f['duration_h']} h"
                   f" · {f['stops']} stop(s)")
        out.append(f"- One-way fare: ${f['fare_low']}–${f['fare_high']} per person ({f['cabin']})")
        out += [f"- {a}" for a in f["advice"]]
    else:
        out.append(f"- {f.get('note', 'Unavailable')}")

    w = trip.get("weather") or {}
    out += ["", "## Weather"]
    if w.get("available"):
        out.append(f"- {w['label']}: highs ~{w['avg_hi']}°C / lows ~{w['avg_lo']}°C")
        out += [f"- {a}" for a in w["advice"]]
    else:
        out.append(f"- {w.get('note', 'Unavailable')}")

    out += ["", "## Hotels"]
    for h in (trip.get("hotels") or {}).get("hotels", []):
        out.append(f"- **{h['name']}** ({h['area']}) — ~${round(h['price_per_night'])}/night. {h['why']}")

    out += ["", "## Itinerary"]
    for d in it["days"]:
        out += [f"### Day {d['day']} — {d['title']}",
                f"- **Morning:** {d['morning']}",
                f"- **Afternoon:** {d['afternoon']}",
                f"- **Evening:** {d['evening']}"]
        if d.get("tip"):
            out.append(f"- *Tip:* {d['tip']}")
        out.append("")

    out += ["## Budget", f"**Total: ${b['total']:,}** (${b['per_person']:,}/person)", ""]
    out += [f"- {x['label']}: ${x['amount']:,}" for x in b["items"]]
    out += ["", f"_{b['assumptions']}_", ""]
    if it.get("packing"):
        out += ["## Packing", *[f"- {p}" for p in it["packing"]], ""]
    if it.get("tips"):
        out += ["## Tips", *[f"- {t}" for t in it["tips"]], ""]
    return "\n".join(out)
