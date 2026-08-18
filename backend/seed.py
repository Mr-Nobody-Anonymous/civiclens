"""Seed CivicLens Ethiopia with organizations, routing rules, demo users and
clearly-labelled demo reports around Addis Ababa and other Ethiopian cities.

Usage:  python seed.py            (idempotent — skips if already seeded)
        python seed.py --fresh    (drop & recreate everything)
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from app.db import Base, SessionLocal, engine
from app.models import (Organization, OrganizationRule, OrganizationUser,
                        Report, ReportAIAnalysis, ReportStatusHistory,
                        ReportAssignment, ReportStatus, Role, User)
from app.security import hash_password

ORGS = [
    dict(name="Ethio telecom", name_am="ኢትዮ ቴሌኮም", org_type="Telecom",
         description="National telecom operator — network, internet and telephone services.",
         contact_email="support@ethiotelecom.demo", city=""),
    dict(name="Addis Ababa City Roads Authority", name_am="የአዲስ አበባ ከተማ መንገዶች ባለስልጣን",
         org_type="Roads/Public Works",
         description="Construction and maintenance of city roads, bridges and walkways.",
         contact_email="roads@aacra.demo", city="Addis Ababa"),
    dict(name="Addis Ababa Water & Sewerage Authority", name_am="የአዲስ አበባ ውሃና ፍሳሽ ባለስልጣን",
         org_type="Water Utility",
         description="Drinking water supply and sewerage services for Addis Ababa.",
         contact_email="water@aawsa.demo", city="Addis Ababa"),
    dict(name="Ethiopian Electric Utility", name_am="የኢትዮጵያ ኤሌክትሪክ አገልግሎት",
         org_type="Electric Utility",
         description="Electric distribution, street lighting and outage response.",
         contact_email="power@eeu.demo", city=""),
    dict(name="Addis Ababa Education Bureau", name_am="የአዲስ አበባ ትምህርት ቢሮ",
         org_type="Education Bureau",
         description="Public schools and education infrastructure.",
         contact_email="education@aaeb.demo", city="Addis Ababa"),
    dict(name="Addis Ababa City Administration", name_am="የአዲስ አበባ ከተማ አስተዳደር",
         org_type="Municipality",
         description="Sanitation, public buildings, safety and general city services.",
         contact_email="city@addisababa.demo", city="Addis Ababa"),
    dict(name="Environmental Protection Authority", name_am="የአካባቢ ጥበቃ ባለስልጣን",
         org_type="Environment Bureau",
         description="Environmental protection, pollution control and green areas.",
         contact_email="epa@epa.demo", city=""),
]

RULES = [
    ("Telecom", "Ethio telecom", "network,internet,signal,fiber,sim,call", "", 10, True),
    ("Roads & Transportation", "Addis Ababa City Roads Authority", "pothole,road,asphalt,bridge,sidewalk", "Addis Ababa", 10, False),
    ("Water", "Addis Ababa Water & Sewerage Authority", "pipe,leak,burst,shortage,sewage", "Addis Ababa", 10, False),
    ("Electricity", "Ethiopian Electric Utility", "power,outage,streetlight,transformer,wire", "", 10, True),
    ("Education", "Addis Ababa Education Bureau", "school,classroom,student,teacher", "Addis Ababa", 10, False),
    ("Garbage & Sanitation", "Addis Ababa City Administration", "garbage,waste,trash,dump", "Addis Ababa", 10, False),
    ("Public Buildings", "Addis Ababa City Administration", "", "Addis Ababa", 20, False),
    ("Safety", "Addis Ababa City Administration", "", "Addis Ababa", 20, False),
    ("Environment", "Environmental Protection Authority", "pollution,river,tree,smoke", "", 10, False),
    ("Other", "Addis Ababa City Administration", "", "", 90, False),
]

# (title, description, category, issue_type, severity, confidence, urgency, status, org,
#  lat, lng, address, city, days_ago)
DEMO_REPORTS = [
    ("Large pothole blocking traffic on Bole Road",
     "A very large and deep pothole has formed on Bole Road near Edna Mall. Cars are swerving "
     "dangerously to avoid it and two accidents almost happened this morning. It is on the main "
     "lane used by thousands of vehicles daily.",
     "Roads & Transportation", "Pothole", 4, 0.93, "high", "in_progress",
     "Addis Ababa City Roads Authority", 8.9936, 38.7873, "Bole Road, near Edna Mall", "Addis Ababa", 6),
    ("Overflowing garbage container near Merkato",
     "The communal garbage container at the Merkato Atikilt Tera entrance has been overflowing "
     "for more than a week. Waste is spreading onto the road and the smell is affecting shops "
     "and pedestrians. Rats have been seen in the area.",
     "Garbage & Sanitation", "Overflowing Garbage", 3, 0.88, "medium", "assigned",
     "Addis Ababa City Administration", 9.0336, 38.7278, "Merkato, Atikilt Tera", "Addis Ababa", 9),
    ("Broken streetlights on Churchill Avenue",
     "Five consecutive streetlights are not working on Churchill Avenue between the Post Office "
     "and Tewodros Square. The street is completely dark at night and pedestrians feel unsafe.",
     "Electricity", "Broken Streetlight", 3, 0.9, "medium", "assigned",
     "Ethiopian Electric Utility", 9.0227, 38.7469, "Churchill Avenue", "Addis Ababa", 4),
    ("No mobile network in Gerji area for three days",
     "Mobile network and internet service has been completely down in the Gerji Mebrat Haile "
     "area for three days. Businesses cannot process mobile payments and residents cannot make "
     "calls. Many people are affected.",
     "Telecom", "Network Outage", 4, 0.91, "high", "under_review",
     "Ethio telecom", 9.0068, 38.8266, "Gerji Mebrat Haile", "Addis Ababa", 3),
    ("Collapsed classroom roof at public school in Gulele",
     "Part of the roof of a grade 4 classroom collapsed after heavy rain at a public primary "
     "school in Gulele sub-city. Luckily it happened at night. 60 students now have no "
     "classroom and the remaining structure looks unsafe.",
     "Education", "Damaged Classroom", 5, 0.95, "critical", "in_progress",
     "Addis Ababa Education Bureau", 9.0605, 38.7273, "Gulele Sub-city, Woreda 3", "Addis Ababa", 12),
    ("Water pipe burst flooding street in Piassa",
     "A main water pipe burst near Piassa Arada Building. Clean drinking water has been flowing "
     "onto the street for two days and the road is flooded. Water pressure in nearby homes has "
     "dropped badly.",
     "Water", "Pipe Burst", 4, 0.92, "high", "resolved",
     "Addis Ababa Water & Sewerage Authority", 9.0348, 38.7525, "Piassa, Arada", "Addis Ababa", 20),
    ("Damaged sidewalk dangerous for pedestrians near Meskel Square",
     "The sidewalk on the north side of Meskel Square has broken concrete slabs with exposed "
     "metal bars. Elderly people and children have tripped. It is a very busy pedestrian route.",
     "Roads & Transportation", "Damaged Sidewalk", 3, 0.87, "medium", "under_review",
     "Addis Ababa City Roads Authority", 9.0105, 38.7614, "Meskel Square", "Addis Ababa", 2),
    ("Open manhole on school route in Kazanchis",
     "A manhole cover has been stolen on the street behind the UNECA compound in Kazanchis. "
     "The open hole is on a route children use to walk to school. Someone placed a tree branch "
     "in it but it is still very dangerous at night.",
     "Safety", "Open Manhole", 5, 0.94, "critical", "assigned",
     "Addis Ababa City Administration", 9.0180, 38.7699, "Kazanchis, behind UNECA", "Addis Ababa", 1),
    ("Sewage overflow into Akaki river",
     "Untreated sewage is flowing directly into the Akaki river near the Kality bridge. The "
     "smell is strong and downstream farmers use this water for vegetables.",
     "Environment", "River Pollution", 4, 0.89, "high", "under_review",
     "Environmental Protection Authority", 8.9163, 38.7597, "Kality Bridge, Akaki River", "Addis Ababa", 5),
    ("Frequent power cuts in Bahir Dar Kebele 14",
     "Electricity goes out 4-5 times every day in Kebele 14, Bahir Dar, damaging appliances. "
     "The local transformer makes loud noises and sparks were seen last night.",
     "Electricity", "Damaged Transformer", 4, 0.86, "high", "submitted",
     None, 11.5936, 37.3908, "Kebele 14", "Bahir Dar", 0),
    ("Uncollected waste near Hawassa lakeshore",
     "Piles of plastic waste near the Hawassa lakeshore recreation area have not been collected "
     "for two weeks. Some of it is blowing into the lake.",
     "Garbage & Sanitation", "Uncollected Waste", 3, 0.84, "medium", "submitted",
     None, 7.0504, 38.4762, "Lakeshore recreation area", "Hawassa", 1),
    ("Slow internet in Adama industrial area",
     "Fiber internet in the Adama industrial zone has been extremely slow for a week, "
     "affecting several factories' operations.",
     "Telecom", "Poor Connectivity", 2, 0.8, "low", "resolved",
     "Ethio telecom", 8.5410, 39.2705, "Industrial zone", "Adama", 15),
    ("Blocked drainage causing street flooding in Dire Dawa",
     "The storm drainage on Sabian main street is completely blocked with sand and waste. "
     "Yesterday's rain flooded the street and water entered three shops. The rainy season "
     "is coming and it will get much worse.",
     "Roads & Transportation", "Drainage / Flooding", 4, 0.87, "high", "under_review",
     None, 9.5931, 41.8661, "Sabian, main street", "Dire Dawa", 2),
    ("Street lighting completely absent in Mekelle Hawelti area",
     "The whole Hawelti roundabout area has no working street lights. Residents avoid "
     "walking after dark and there have been robberies reported.",
     "Electricity", "Broken Streetlight", 3, 0.85, "medium", "submitted",
     None, 13.4967, 39.4697, "Hawelti roundabout", "Mekelle", 1),
    ("Broken water fountain and pipes at Gondar Fasil area",
     "Public water point near the Fasil Ghebbi entrance has been broken for a month. "
     "Residents walk far for water and the leak wastes water all day.",
     "Water", "Water Leak", 3, 0.83, "medium", "under_review",
     None, 12.6075, 37.4661, "Near Fasil Ghebbi", "Gondar", 4),
    ("Waste collection stopped in Jimma Ginjo area",
     "Household waste has not been collected in Ginjo kebele for over two weeks. "
     "People are burning waste in the street which creates smoke problems.",
     "Garbage & Sanitation", "Uncollected Waste", 3, 0.86, "medium", "submitted",
     None, 7.6733, 36.8344, "Ginjo Kebele", "Jimma", 1),
]


def seed(fresh=False):
    from app.config import settings
    # ---- production safety gates ----
    if settings.env == "production" and (settings.seed_demo_data or settings.create_demo_accounts):
        print("REFUSING to seed demo data: CL_ENV=production but CL_SEED_DEMO_DATA / "
              "CL_CREATE_DEMO_ACCOUNTS are not explicitly false. In production run with\n"
              "  CL_SEED_DEMO_DATA=false CL_CREATE_DEMO_ACCOUNTS=false python seed.py\n"
              "to create only organizations+rules, and create the first admin with:\n"
              "  python create_admin.py <email> <name>")
        raise SystemExit(2)
    if not settings.seed_demo_data and not settings.create_demo_accounts:
        seed_base_only()
        return
    if fresh:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Organization).first():
            print("Already seeded — skipping (seed is idempotent). Use --fresh to reseed.")
            return
        print("NOTE: demo accounts below are DEVELOPMENT-ONLY. Disable or delete them "
              "before production deployment (see PRODUCTION.md).")

        orgs = {}
        for o in ORGS:
            org = Organization(**o)
            db.add(org)
            orgs[o["name"]] = org
        db.commit()

        for cat, orgname, kws, city, prio, auto in RULES:
            db.add(OrganizationRule(category=cat, organization_id=orgs[orgname].id,
                                    keywords=kws, city=city or None, priority=prio,
                                    auto_assign=auto))
        db.commit()

        # ---- users (demo credentials; passwords hashed) ----
        users = {}
        for name, email, role, pw in [
            ("Admin User", "admin@civiclens.et", Role.admin, "admin12345"),
            ("Meron Tadesse (Moderator)", "moderator@civiclens.et", Role.moderator, "moderator123"),
            ("Dawit Bekele (Ethio telecom)", "staff@ethiotelecom.et", Role.org_staff, "telecom123"),
            ("Sara Alemu (Roads Authority)", "staff@roads.et", Role.org_staff, "roads12345"),
            ("Abebe Kebede (Citizen)", "citizen@example.et", Role.citizen, "citizen123"),
        ]:
            u = User(name=name, email=email, role=role, password_hash=hash_password(pw),
                     city="Addis Ababa", language="en")
            db.add(u)
            users[email] = u
        db.commit()
        db.add(OrganizationUser(organization_id=orgs["Ethio telecom"].id,
                                user_id=users["staff@ethiotelecom.et"].id, org_role="manager"))
        db.add(OrganizationUser(organization_id=orgs["Addis Ababa City Roads Authority"].id,
                                user_id=users["staff@roads.et"].id, org_role="manager"))
        db.commit()

        # ---- demo reports ----
        now = datetime.now(timezone.utc)
        citizen = users["citizen@example.et"]
        for (title, desc, cat, itype, sev, conf, urg, status, orgname,
             lat, lng, addr, city, days_ago) in DEMO_REPORTS:
            created = now - timedelta(days=days_ago, hours=random.randint(0, 20))
            r = Report(title=title, description=desc, category=cat, user_category=cat,
                       issue_type=itype, severity=sev, status=ReportStatus(status),
                       city=city, latitude=lat, longitude=lng, address=addr,
                       reporter_id=citizen.id, is_demo=True, created_at=created,
                       organization_id=orgs[orgname].id if orgname else None)
            if status == "resolved":
                r.resolved_at = created + timedelta(days=random.randint(1, 6))
            db.add(r)
            db.commit()
            db.add(ReportAIAnalysis(
                report_id=r.id, category=cat, issue_type=itype, severity=sev,
                confidence=conf, urgency=urg,
                responsible_organization=orgname or "Unrouted",
                organization_type=orgs[orgname].org_type if orgname else None,
                reasoning=f"Demo analysis: text signals strongly match '{cat}'. "
                          f"Severity {sev}/5 based on danger indicators and number of people affected.",
                model_name="civiclens-heuristic", model_version="1.2",
                frames_analyzed=random.randint(0, 3), created_at=created + timedelta(minutes=2)))
            db.add(ReportStatusHistory(report_id=r.id, to_status="submitted",
                                       note="Report submitted (demo data)", created_at=created))
            db.add(ReportStatusHistory(report_id=r.id, from_status="submitted",
                                       to_status="ai_analysis", note="AI analysis started",
                                       created_at=created + timedelta(minutes=1)))
            if status not in ("submitted", "ai_analysis"):
                db.add(ReportStatusHistory(report_id=r.id, from_status="ai_analysis",
                                           to_status=status,
                                           note=f"Routed to {orgname}" if orgname else "Awaiting triage",
                                           created_at=created + timedelta(minutes=5)))
            if orgname:
                db.add(ReportAssignment(report_id=r.id, organization_id=orgs[orgname].id,
                                        source="rule", note="Routed by demo rule",
                                        created_at=created + timedelta(minutes=5)))
            db.commit()

        print("Seeded:", len(ORGS), "orgs,", len(RULES), "rules,", len(DEMO_REPORTS), "demo reports.")
        print("\nDemo accounts:")
        print("  admin@civiclens.et / admin12345          (Administrator)")
        print("  moderator@civiclens.et / moderator123    (Moderator)")
        print("  staff@ethiotelecom.et / telecom123       (Ethio telecom staff)")
        print("  staff@roads.et / roads12345              (Roads Authority staff)")
        print("  citizen@example.et / citizen123          (Citizen)")
    finally:
        db.close()


def seed_base_only():
    """Production-safe seed: organizations + routing rules only. No demo
    reports, no demo accounts. Idempotent."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Organization).first():
            print("Base data already present — skipping.")
            return
        orgs = {}
        for o in ORGS:
            org = Organization(**o)
            db.add(org)
            orgs[o["name"]] = org
        db.commit()
        for cat, orgname, kws, city, prio, auto in RULES:
            db.add(OrganizationRule(category=cat, organization_id=orgs[orgname].id,
                                    keywords=kws, city=city or None, priority=prio,
                                    auto_assign=auto))
        db.commit()
        print(f"Base seed complete: {len(ORGS)} organizations, {len(RULES)} routing rules. "
              "No demo data created. Create the first admin with: python create_admin.py")
    finally:
        db.close()


if __name__ == "__main__":
    seed(fresh="--fresh" in sys.argv)
