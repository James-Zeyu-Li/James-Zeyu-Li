#!/usr/bin/env python3
import os
import re
import base64
import requests
from typing import Iterable, List, Dict, Set, Optional

# ======= 配置（可被 README 注释与环境变量覆盖） =======
# 改成你的 GitHub 用户名，或用 Actions 环境变量覆盖
USER = os.getenv("PROFILE_USERNAME", "zeyuli")
MAX_ROWS = int(os.getenv("MAX_PROJECT_ROWS", "10"))

# 代码内默认白/黑名单（可留空，用 README/ENV 覆盖）
INCLUDE_REPOS_DEFAULT: Set[str] = {
    "CS6650_2025_TA", "profolio_website", "High-Concurrency-CQRS-Ticketing-Platform",
    "CedarArbutusCode", "LocalSimulationKG", "CS6650_scalable_distributed",
    "DistributedAlbumStorage", "VirtualMemorySimulator", "ConcurrencyTesting"
}
EXCLUDE_REPOS_DEFAULT: Set[str] = set()

API_LIST = f"https://api.github.com/users/{USER}/repos?per_page=100&sort=updated&direction=desc"
HEAD = {
    # GITHUB_TOKEN 在 GitHub Actions 内置；本地跑可以注释掉 Authorization
    **({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.getenv("GITHUB_TOKEN") else {}),
    "X-GitHub-Api-Version": "2022-11-28",
    "Accept": "application/vnd.github+json",
    "User-Agent": f"{USER}-profile-techstack-script"
}

# ======= HTTP/Tools =======


def fetch_all(url: str) -> List[dict]:
    """支持 Link 分页抓取所有结果。"""
    out, next_url = [], url
    sess = requests.Session()
    while next_url:
        r = sess.get(next_url, headers=HEAD, timeout=30)
        r.raise_for_status()
        out.extend(r.json())
        # 解析 Link 头
        link = r.headers.get("Link", "")
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        next_url = m.group(1) if m else None
    return out


def fetch_json(url: str) -> dict:
    r = requests.get(url, headers=HEAD, timeout=30)
    r.raise_for_status()
    return r.json()


def get_file(repo_full: str, path: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{repo_full}/contents/{path}"
    r = requests.get(url, headers=HEAD, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "ignore")
    return None


# ======= README 解析 =======
README_PATH = "README.md"
INCLUDE_DIRECTIVE = r"<!--TECH-STACK:INCLUDE=([^>]+)-->"
EXCLUDE_DIRECTIVE = r"<!--TECH-STACK:EXCLUDE=([^>]+)-->"


def parse_list_directive(txt: str, pattern: str) -> Set[str]:
    m = re.search(pattern, txt, flags=re.I)
    if not m:
        return set()
    # 允许空格，去重
    return {x.strip() for x in m.group(1).split(",") if x.strip()}


def load_readme_controls() -> (Set[str], Set[str]):
    try:
        with open(README_PATH, "r", encoding="utf-8") as f:
            txt = f.read()
    except FileNotFoundError:
        return set(), set()
    return parse_list_directive(txt, INCLUDE_DIRECTIVE), parse_list_directive(txt, EXCLUDE_DIRECTIVE)

# ======= 技术栈识别 =======


def detect_stack(repo: dict) -> List[str]:
    repo_full = repo["full_name"]
    files = {
        "go.mod": get_file(repo_full, "go.mod"),
        "pom.xml": get_file(repo_full, "pom.xml"),
        "build.gradle": get_file(repo_full, "build.gradle"),
        "package.json": get_file(repo_full, "package.json"),
        "requirements.txt": get_file(repo_full, "requirements.txt"),
        "Dockerfile": get_file(repo_full, "Dockerfile"),
    }
    tech: Set[str] = set()
    lang = repo.get("language")
    if lang:
        tech.add(lang)

    if files["go.mod"]:
        tech.add("Go")
        if re.search(r'\bgin-gonic/gin\b', files["go.mod"]):
            tech.add("Gin")

    if files["pom.xml"] or files["build.gradle"]:
        tech.update(["Java", "Spring Boot"])
        if files["pom.xml"] and "spring-boot-starter-web" in files["pom.xml"]:
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
    for kw, label in [
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
    ]:
        if re.search(kw, blob, re.I):
            tech.add(label)

    return sorted(tech)

# ======= 渲染 & 写回 =======


def escape_pipes(s: str) -> str:
    return s.replace("|", r"\|")


def build_table(rows: List[Dict[str, str]]) -> str:
    header = "| Project | Tech |\n|---|---|\n"
    lines = []
    for r in rows:
        name = escape_pipes(r["name"])
        url = r["html_url"]
        techs = " · ".join(r["tech"]) if r["tech"] else "-"
        lines.append(f"| [{name}]({url}) | {techs} |")
    return header + "\n".join(lines)


START_TAG = "<!--TECH-STACK:START-->"
END_TAG = "<!--TECH-STACK:END-->"


def update_readme(table: str) -> None:
    with open(README_PATH, "r+", encoding="utf-8") as f:
        txt = f.read()
        block = f"{START_TAG}\n{table}\n{END_TAG}"
        if START_TAG in txt and END_TAG in txt:
            txt = re.sub(
                f"{re.escape(START_TAG)}.*?{re.escape(END_TAG)}", block, txt, flags=re.S)
        else:
            txt += f"\n\n## Recent Projects & Tech\n{block}\n"
        f.seek(0)
        f.write(txt)
        f.truncate()

# ======= 主流程 =======


def effective_sets() -> (Set[str], Set[str]):
    # 从 README 注释获取
    inc_rd, exc_rd = load_readme_controls()

    # 从环境变量获取（逗号分隔）
    inc_env = {x.strip() for x in os.getenv(
        "TECHSTACK_INCLUDE", "").split(",") if x.strip()}
    exc_env = {x.strip() for x in os.getenv(
        "TECHSTACK_EXCLUDE", "").split(",") if x.strip()}

    include = inc_rd or inc_env or INCLUDE_REPOS_DEFAULT
    exclude = exc_rd or exc_env or EXCLUDE_REPOS_DEFAULT
    return include, exclude


def main() -> None:
    include, exclude = effective_sets()

    repos = fetch_all(API_LIST)
    # 过滤：非 fork、非私有、非归档/禁用/模板
    repos = [
        r for r in repos
        if not r.get("fork", False)
        and not r.get("private", False)
        and not r.get("archived", False)
        and not r.get("disabled", False)
        and not r.get("is_template", False)
    ]

    # 白名单优先：若 include 非空，仅取其交集；否则视为“全量-黑名单”
    if include:
        repos = [r for r in repos if r["name"] in include]
    if exclude:
        repos = [r for r in repos if r["name"] not in exclude]

    # 取前 MAX_ROWS 个
    rows = []
    for r in repos[:MAX_ROWS]:
        rows.append({
            "name": r["name"],
            "html_url": r["html_url"],
            "tech": detect_stack(r)
        })

    update_readme(build_table(rows))


if __name__ == "__main__":
    main()
