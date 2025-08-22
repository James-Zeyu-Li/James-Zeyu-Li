#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import base64
import requests
import time
from typing import List, Dict, Set, Optional
from collections import Counter

USER = os.getenv("PROFILE_USERNAME", "James-Zeyu-Li")
READ_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
TIMEOUT = 30

# ---- 只读白名单 ----
INCLUDE_REPOS: Set[str] = {
    "CS6650_2025_TA", "profolio_website", "High-Concurrency-CQRS-Ticketing-Platform",
    "CedarArbutusCode", "LocalSimulationKG", "CS6650_scalable_distributed",
    "DistributedAlbumStorage", "VirtualMemorySimulator", "ConcurrencyTesting"
}

# README 占位符
STACK_START, STACK_END = "<!--TECH-STACK:START-->", "<!--TECH-STACK:END-->"
SUM_START,   SUM_END = "<!--TECH-SUMMARY:START-->", "<!--TECH-SUMMARY:END-->"
PROJ_START,  PROJ_END = "<!--TECH-PROJECT-SHARE:START-->", "<!--TECH-PROJECT-SHARE:END-->"
README_PATH = "README.md"

GITHUB = "https://api.github.com"
HEAD = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": f"{USER}-techstack-aggregator"
}
if READ_TOKEN:
    HEAD["Authorization"] = f"Bearer {READ_TOKEN}"

sess = requests.Session()
sess.headers.update(HEAD)


def fetch_all_repos(username: str) -> List[Dict]:
    out, page = [], 1
    while True:
        url = f"{GITHUB}/users/{username}/repos?type=owner&sort=updated&per_page=100&page={page}"
        r = sess.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        arr = r.json()
        if not arr:
            break
        out.extend(arr)
        page += 1
        time.sleep(0.15)
    return out


def get_file(full: str, path: str) -> Optional[str]:
    url = f"{GITHUB}/repos/{full}/contents/{path}"
    r = sess.get(url, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "ignore")
    return None


def get_languages_bytes(full: str) -> Dict[str, int]:
    url = f"{GITHUB}/repos/{full}/languages"
    r = sess.get(url, timeout=TIMEOUT)
    return r.json() if r.status_code == 200 else {}


TECH_KWS = [
    (r'\bredis\b', "Redis"),
    (r'\brabbitmq\b', "RabbitMQ"),
    (r'\b(dynamodb|aws dynamodb)\b', "DynamoDB"),
    (r'\bpostgres(ql)?\b', "PostgreSQL"),
    (r'\bmysql\b', "MySQL"),
    (r'\bmongodb\b', "MongoDB"),
    (r'\baws\b', "AWS"),
    (r'\bterraform\b', "Terraform"),
    (r'\bkubernetes|k8s\b', "Kubernetes"),
    (r'\bnginx\b', "Nginx"),
    (r'\bgrpc\b', "gRPC"),
]


def detect_repo_tech(repo_full: str) -> List[str]:
    files = {
        "go.mod": get_file(repo_full, "go.mod"),
        "pom.xml": get_file(repo_full, "pom.xml"),
        "build.gradle": get_file(repo_full, "build.gradle"),
        "package.json": get_file(repo_full, "package.json"),
        "requirements.txt": get_file(repo_full, "requirements.txt"),
        "Dockerfile": get_file(repo_full, "Dockerfile"),
    }
    tech = set()
    if files["go.mod"]:
        tech.add("Go")
        if re.search(r'\bgin-gonic/gin\b', files["go.mod"]):
            tech.add("Gin")
    if files["pom.xml"] or files["build.gradle"]:
        tech.update(["Java", "Spring Boot"])
        if files["pom.xml"] and "spring-boot-starter-web" in (files["pom.xml"] or ""):
            tech.add("REST")
    if files["package.json"]:
        tech.update(["Node.js", "NPM"])
        if re.search(r'"next"\s*:', files["package.json"]):
            tech.add("Next.js")
        if re.search(r'"react"\s*:', files["package.json"]):
            tech.add("React")
    if files["requirements.txt"]:
        tech.add("Python")
        if re.search(r'\bfastapi\b', files["requirements.txt"]):
            tech.add("FastAPI")
        if re.search(r'\bflask\b', files["requirements.txt"]):
            tech.add("Flask")
    if files["Dockerfile"]:
        tech.add("Docker")
        if re.search(r'FROM\s+nginx', files["Dockerfile"], re.I):
            tech.add("Nginx")

    readme = get_file(repo_full, "README.md") or ""
    blob = " ".join((readme, *(files[k] or "" for k in files)))
    for kw, label in TECH_KWS:
        if re.search(kw, blob, re.I):
            tech.add(label)
    return sorted(tech)


def escape_pipes(s: str) -> str:
    return s.replace("|", r"\|")


def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    v = float(n)
    for u in units:
        if v < 1024 or u == "GB":
            return f"{v:.1f} {u}"
        v /= 1024


def build_project_table(rows: List[Dict]) -> str:
    header = "| Project | Tech |\n|---|---|\n"
    body = "\n".join(f"| [{escape_pipes(r['name'])}]({r['url']}) | {' · '.join(r['tech']) if r['tech'] else '-'} |"
                     for r in rows)
    return header + body


def fmt_pct(num: int, den: int) -> str:
    return "0.0%" if den <= 0 else f"{(num*100.0/den):.1f}%"


def build_summary_tables(lang_bytes_total: Dict[str, int],
                         tech_presence: Dict[str, int],
                         repo_count: int) -> str:
    # Languages (by bytes)
    lang_rows = sorted(lang_bytes_total.items(),
                       key=lambda kv: kv[1], reverse=True)
    lang_sum = sum(v for _, v in lang_rows) or 1
    lang_md = "| Language | Share |\n|---|---|\n" + "\n".join(
        f"| {escape_pipes(k)} | {v*100.0/lang_sum:.1f}% |" for k, v in lang_rows
    )
    # Tech adoption (% repos)
    tech_rows = sorted(tech_presence.items(),
                       key=lambda kv: kv[1], reverse=True)
    tech_md = "| Tech | Adoption |\n|---|---|\n" + "\n".join(
        f"| {escape_pipes(k)} | {fmt_pct(v, repo_count)} |" for k, v in tech_rows
    )
    return (
        "### Overall Tech Usage\n\n"
        "**Languages (by bytes across selected repos)**\n\n" + lang_md +
        "\n\n**Tech adoption (share of repos using the tech)**\n\n" +
        tech_md + "\n"
    )


def build_project_share_table(project_bytes: List[Dict]) -> str:
    # project_bytes = [{name,url,bytes}]
    total = sum(p["bytes"] for p in project_bytes) or 1
    header = "| Project | Code Size | Share |\n|---|---:|---:|\n"
    rows = []
    for p in sorted(project_bytes, key=lambda x: x["bytes"], reverse=True):
        rows.append(
            f"| [{escape_pipes(p['name'])}]({p['url']}) | {human_bytes(p['bytes'])} | {p['bytes']*100.0/total:.1f}% |")
    return header + "\n".join(rows)


def update_readme(stack_table: str, summary_block: str, project_share_md: str):
    with open(README_PATH, "r+", encoding="utf-8") as f:
        txt = f.read()

        def replace_block(txt, start, end, body):
            block = f"{start}\n{body}\n{end}"
            if start in txt and end in txt:
                return re.sub(re.escape(start) + r".*?" + re.escape(end), block, txt, flags=re.S)
            else:
                # 默认插入在文末
                return txt + f"\n\n{block}\n"

        txt = replace_block(txt, STACK_START, STACK_END, stack_table)
        txt = replace_block(txt, SUM_START,   SUM_END,   summary_block)
        txt = replace_block(txt, PROJ_START,  PROJ_END,  project_share_md)

        f.seek(0)
        f.write(txt)
        f.truncate()


def main():
    all_repos = fetch_all_repos(USER)
    selected = [
        r for r in all_repos
        if (r["name"] in INCLUDE_REPOS)
        and not r.get("fork", False)
        and not r.get("private", False)
        and not r.get("archived", False)
        and not r.get("disabled", False)
        and not r.get("is_template", False)
    ]

    rows = []
    tech_presence: Dict[str, int] = Counter()
    lang_bytes_total: Dict[str, int] = Counter()
    project_bytes: List[Dict] = []

    for r in selected:
        full = r["full_name"]
        techs = detect_repo_tech(full)
        rows.append({"name": r["name"], "url": r["html_url"], "tech": techs})

        lang_bytes = get_languages_bytes(full)
        repo_total_bytes = sum(int(v) for v in lang_bytes.values())
        project_bytes.append(
            {"name": r["name"], "url": r["html_url"], "bytes": repo_total_bytes})

        for k, v in lang_bytes.items():
            lang_bytes_total[k] += int(v)

        for t in set(techs):
            tech_presence[t] += 1

    stack_table = build_project_table(rows)
    summary_md = build_summary_tables(
        lang_bytes_total, tech_presence, len(selected))
    project_md = build_project_share_table(project_bytes)
    update_readme(stack_table, summary_md, project_md)


if __name__ == "__main__":
    main()
