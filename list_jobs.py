from tracker import JobTracker

t = JobTracker()
jobs = [j for j in t.all_jobs() if j["source"] in ("Greenhouse", "Lever") and not j["applied"]]
t.close()

print(f"Found {len(jobs)} unapplied Greenhouse/Lever jobs:\n")
for i, j in enumerate(jobs[:10]):
    print(f"[{i}] [{j['source']:12s}] {j['company']:20s}  {j['title'][:50]}")
    print(f"     {j['url']}\n")
