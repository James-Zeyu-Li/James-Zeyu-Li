#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate compact tech tables into README:
- Recent Projects (Tech × Code mix)
- Tech Summary (Languages overall + Tech adoption)
Design notes:
- Manual run only (workflow_dispatch)
- Whitelist repositories; render in the given order
- Tech override for certain repos (e.g., "Computer Systems")
- Language alias: HCL -> Terraform (HCL)
- Idempotent: overwrite content between START/END markers
"""

import os
import re
import base64
import time
from typing import List, Dict, Optional
from collections import Counter

import requests

# ===== Basic config =====
USER: str = os.getenv("PROFILE_USERNAME", "James-Zeyu-Li")
TOKEN: str = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
TIMEOUT = 30

# --- Language alias (GitHub /languages returns "HCL" for .tf) ---
HCL_LABEL = "Terraform (HCL)"
LANG_ALIAS: Dict[str, str] = {
    "HCL": HCL_LABEL,
}


def normalize_langs(lang_bytes: Dict[str, int]) -> Dict[str, int]:
    """Alias & merge language bytes (e.g., HCL -> Terraform (HCL))."""
    out: Counter = Counter()
    for k, v in (lang_bytes or {}).items():
        out[LANG_ALIAS.get(k, k)] += int(v)
    return dict(out)


# ===== Whitelist (render in this order) =====
INCLUDE_REPOS: List[str] = [
    "CS6650_2025_TA",
    "High-Concurrency-CQRS-Ticketing-Platform",
    "CedarArbutusCode",
    # "LocalSimulationKG",
    "DistributedAlbumStorage",
    "ConcurrencyTesting",
    "VirtualMemorySimulator",
    "profolio_website",
    # "CS6650_scalable_distributed",
]

# ===== Tech override by repo (exact name match) =====
# NOTE: override means "replace" (not union). To append instead:
# techs = sorted(set(detect_tech(full)) | set(TECH_OVERRIDE.get(name, [])))
TECH_OVERRIDE: Dict[str, List[str]] = {
    "ConcurrencyTesting": ["Computer Systems"],
    "VirtualMemorySimulator": ["Computer Systems"],
}

# ===== README anchors (two blocks only) =====
PJT_START, PJT_END = "<!--TECH-PROJECTS:START-->", "<!--TECH-PROJECTS:END-->"
OVR_START, OVR_END = "<!--TECH-OVERALL:START-->", "<!--TECH-OVERALL:END-->"
README = "README.md"

# ===== Rendering params =====
TOP_LANGS = 6
TOP_TECHS = 10
BAR_W_PROJECT = 10
BAR_W_OVERALL = 12
TECH_PER_ROW = 5

# ===== HTTP =====
GITHUB = "https://api.github.com"
HEAD = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": f"{USER}-tech-agg"
}
if TOKEN:
    HEAD["Authorization"] = f"Bearer {TOKEN}"
sess = requests.Session()
sess.headers.update(HEAD)

# ---------- HTTP helpers ----------


def list_owner_repos(user: str) -> Dict[str, dict]:
    """Return {repo_name: repo_obj} for owner's repositories (filtered)."""
    out, page = [], 1
    while True:
        url = f"{GITHUB}/users/{user}/repos?type=owner&sort=updated&per_page=100&page={page}"
        r = sess.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        arr = r.json()
        if not arr:
            break
        out.extend(arr)
        page += 1
        time.sleep(0.1)
    keep: Dict[str, dict] = {}
    for r in out:
        if r.get("fork") or r.get("private") or r.get("archived") or r.get("disabled") or r.get("is_template"):
            continue
        keep[r["name"]] = r
    return keep


def get_file(full: str, path: str) -> Optional[str]:
    r = sess.get(f"{GITHUB}/repos/{full}/contents/{path}", timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "ignore")
    return None


def get_languages(full: str) -> Dict[str, int]:
    r = sess.get(f"{GITHUB}/repos/{full}/languages", timeout=TIMEOUT)
    return r.json() if r.status_code == 200 else {}


# ---------- Tech detection ----------
KWS = [
    (r'\bredis\b', "Redis"), (r'\brabbitmq\b', "RabbitMQ"), (r'\bkafka\b', "Kafka"),
    (r'\b(dynamodb|aws dynamodb)\b', "DynamoDB"), (r'\bpostgres(ql)?\b', "PostgreSQL"),
    (r'\bmysql\b', "MySQL"), (r'\bmongodb\b', "MongoDB"), (r'\baws\b', "AWS"),
    (r'\bterraform\b', "Terraform"), (r'\bkubernetes|k8s\b', "Kubernetes"),
    (r'\bnginx\b', "Nginx"), (r'\bgrpc\b', "gRPC"),
    (r'\bfastapi\b', "FastAPI"), (r'\bflask\b', "Flask"),
    (r'\bexpress\b', "Express"), (r'\breact\b',
                                  "React"), (r'\bnext(\.js)?\b', "Next.js"),
    (r'\bspring-boot\b', "Spring Boot"), (r'\bgin-gonic/gin\b', "Gin"),
]
SCAN_FILES = [
    "go.mod", "go.sum",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "package.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "pyproject.toml", "Pipfile", "environment.yml",
    "Dockerfile", "README.md"
]


def detect_tech(full: str) -> List[str]:
    tech = set()
    f = {p: get_file(full, p) for p in SCAN_FILES}
    if f["go.mod"]:
        tech.add("Go")
    if f["pom.xml"] or f["build.gradle"] or f["build.gradle.kts"]:
        tech.update(["Java", "Spring Boot"])
    if f["package.json"]:
        tech.update(["Node.js", "NPM"])
    if f["requirements.txt"] or f["pyproject.toml"]:
        tech.add("Python")
    if f["Dockerfile"]:
        tech.add("Docker")
    blob = " ".join((v or "") for v in f.values())
    for kw, label in KWS:
        if re.search(kw, blob, re.I):
            tech.add(label)
    return sorted(tech)

# ---------- Rendering ----------


def bar(pct: float, width: int) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100.0 * width)
    return "█" * filled + "░" * (width - filled)


def escape(s: str) -> str:
    return s.replace("|", r"\|")


def shorten(techs: List[str], limit: int) -> str:
    if len(techs) <= limit:
        return " · ".join(techs)
    return " · ".join(techs[:limit]) + f" · +{len(techs) - limit}"


def render_code_mix(lang_bytes: Dict[str, int], top: int = 2) -> str:
    total = sum(lang_bytes.values()) or 1
    top_items = sorted(lang_bytes.items(),
                       key=lambda kv: kv[1], reverse=True)[:top]
    if not top_items:
        return "-"
    parts: List[str] = []
    for name, v in top_items:
        pct = v * 100.0 / total
        parts.append(f"{name} {pct:>4.1f}% {bar(pct, BAR_W_PROJECT)}")
    return " / ".join(parts)


def md_projects(rows: List[Dict]) -> str:
    header = "| Project | Tech | Code mix |\n|---|---|---|\n"
    body = "\n".join(
        f"| [{escape(r['name'])}]({r['url']}) | "
        f"{(shorten(r['tech'], TECH_PER_ROW) if r['tech'] else '-') } | "
        f"{render_code_mix(r['lang'])} |"
        for r in rows
    )
    return header + body


def md_overall(lang_total: Dict[str, int], tech_presence: Dict[str, int], repo_cnt: int) -> str:
    # Languages Top-N
    lang_rows = sorted(lang_total.items(), key=lambda kv: kv[1], reverse=True)[
        :TOP_LANGS]
    lang_sum = sum(lang_total.values()) or 1
    lang_md = "| Language | Share |\n|---|---:|\n" + "\n".join(
        f"| {escape(k)} | {v * 100.0 / lang_sum:5.1f}% {bar(v * 100.0 / lang_sum, BAR_W_OVERALL)} |"
        for k, v in lang_rows
    )
    # Tech adoption Top-N
    tech_rows = sorted(tech_presence.items(),
                       key=lambda kv: kv[1], reverse=True)[:TOP_TECHS]
    tech_md = "| Tech | Adoption |\n|---|---:|\n" + "\n".join(
        f"| {escape(k)} | {(v * 100.0 / max(1, repo_cnt)):5.1f}% {bar(v * 100.0 / max(1, repo_cnt), BAR_W_OVERALL)} |"
        for k, v in tech_rows
    )
    note = "<sub>Note: GitHub counts `.tf` as HCL; shown as Terraform for readability.</sub>"
    return "Languages (by bytes across selected repos)\n\n" + lang_md + \
           "\n\nTech adoption (share of selected repos)\n\n" + tech_md + \
           "\n\n" + note


def write_block(txt: str, start: str, end: str, body: str) -> str:
    block = f"{start}\n{body}\n{end}"
    if start in txt and end in txt:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), block, txt, flags=re.S)
    return txt + f"\n\n{block}\n"

# ---------- Main ----------


def main() -> None:
    repo_map = list_owner_repos(USER)  # {name: repo}

    # Preserve the whitelist order
    selected = [repo_map[name] for name in INCLUDE_REPOS if name in repo_map]

    rows: List[Dict] = []
    lang_total: Dict[str, int] = Counter()
    tech_presence: Dict[str, int] = Counter()

    for r in selected:
        full = r["full_name"]

        # 1) Tech override (replace). Switch to "append" if needed (see TECH_OVERRIDE note above).
        techs = TECH_OVERRIDE.get(r["name"]) or detect_tech(full)

        # 2) Languages with alias normalization (HCL -> Terraform (HCL))
        langs_raw = get_languages(full)
        langs = normalize_langs(langs_raw)

        rows.append(
            {"name": r["name"], "url": r["html_url"], "tech": techs, "lang": langs})

        for k, v in langs.items():
            lang_total[k] += int(v)
        for t in set(techs):
            tech_presence[t] += 1

    projects_md = md_projects(rows)
    overall_md = md_overall(lang_total, tech_presence, len(selected))

    with open(README, "r+", encoding="utf-8") as f:
        txt = f.read()
        txt = write_block(txt, PJT_START, PJT_END, projects_md)
        txt = write_block(txt, OVR_START, OVR_END, overall_md)
        f.seek(0)
        f.write(txt)
        f.truncate()


if __name__ == "__main__":
    main()
