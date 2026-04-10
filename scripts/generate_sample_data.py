"""
Generates synthetic historical ticket CSV for seeding Chroma.

Usage:
    python scripts/generate_sample_data.py
"""
import csv
import random
import uuid
from pathlib import Path


TEMPLATES = [
    {
        "title": "Database connection timeout",
        "description": "PostgreSQL read replica times out after 30s under load.",
        "priority": "high",
        "category": "database",
        "resolution_summary": "Increased max_connections to 500 and restarted replica.",
    },
    {
        "title": "VPN not connecting for remote users",
        "description": "Employees cannot establish VPN connections from home networks.",
        "priority": "medium",
        "category": "network",
        "resolution_summary": "Rolled back firewall rule change that blocked UDP 1194.",
    },
    {
        "title": "Email delivery failing",
        "description": "SMTP server refuses new connections. Mail queue is growing.",
        "priority": "high",
        "category": "email",
        "resolution_summary": "Cleared disk space by archiving old logs, restarted Postfix.",
    },
    {
        "title": "High CPU usage on web servers",
        "description": "All web server nodes are at 95%+ CPU. Response times degraded.",
        "priority": "critical",
        "category": "infrastructure",
        "resolution_summary": "Identified runaway cron job and killed it; added CPU alert.",
    },
    {
        "title": "Authentication service returning 500",
        "description": "Login endpoint returns HTTP 500 for all users after latest deploy.",
        "priority": "critical",
        "category": "auth",
        "resolution_summary": "Rolled back deploy v2.3.1 to v2.3.0 via kubectl rollout undo.",
    },
    {
        "title": "SSL certificate expired",
        "description": "The TLS certificate for api.example.com expired causing browser warnings.",
        "priority": "high",
        "category": "security",
        "resolution_summary": "Renewed certificate via Let's Encrypt and reloaded nginx.",
    },
    {
        "title": "Disk usage at 95% on database server",
        "description": "prod-db-01 disk utilization at 95%. Risk of data loss.",
        "priority": "critical",
        "category": "database",
        "resolution_summary": "Archived 60 days of WAL logs to S3; freed 200GB.",
    },
    {
        "title": "CI/CD pipeline failing on main branch",
        "description": "All CI runs on main are failing with exit code 1 on test step.",
        "priority": "medium",
        "category": "devops",
        "resolution_summary": "Fixed flaky test that was asserting on timestamp precision.",
    },
]


def generate(n: int = 50) -> list[dict]:
    rows = []
    for i in range(n):
        template = random.choice(TEMPLATES)
        rows.append({
            "ticket_id": f"hist-{str(uuid.uuid4())[:8]}",
            **template,
        })
    return rows


def main():
    out_dir = Path("data/seed_tickets")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "historical_tickets.csv"

    rows = generate(n=50)
    fieldnames = ["ticket_id", "title", "description", "priority", "category", "resolution_summary"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} synthetic tickets → {out_path}")


if __name__ == "__main__":
    main()
