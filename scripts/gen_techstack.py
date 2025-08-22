#!/usr/bin/env python3
import os
import re
import requests
import base64

USER = "zeyuli"  # 改成你的用户名
API = f"https://api.github.com/users/{USER}/repos?per_page=100&sort=updated"
HEAD = {
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "X-GitHub-Api-Version": "2022-11-28"}


def fetch(url):
    r = requests.get(url, headers=HEAD, timeout=30)
    r.raise_for_status()
    return r.json()


def get_file(repo_full, path):
    url = f"https://api.github.com/repos/{repo_full}/contents/{path}"
    r = requests.get(url, headers=HEAD, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "ignore")
    return None


def detect_stack(repo):
    repo_full = repo["full_name"]
    files = {
        "go.mod": get_file(repo_full, "go.mod"),
        "pom.xml": get_file(repo_full, "pom.xml"),
        "build.gradle": get_file(repo_full, "build.gradle"),
        "package.json": get_file(repo_full, "package.json"),
        "requirements.txt": get_file(repo_full, "requirements.txt"),
        "Dockerfile": get_file(repo_full, "Dockerfile"),
    }
    tech = set()
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
        tech.add("Node.js")
        tech.add("NPM")
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

    # 常见中间件与云（通过 README/代码可加深度分析，这里先简单规则）
    readme = get_file(repo_full, "README.md") or ""
    blob = " ".join((readme or "", *(files[k] or "" for k in files)))
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
    ]:
        if re.search(kw, blob, re.I):
            tech.add(label)

    return sorted(tech)


def build_table(rows):
    header = "| Project | Tech |\n|---|---|\n"
    return header + "\n".join(f"| [{r['name']}]({r['html_url']}) | {' · '.join(r['tech'])} |" for r in rows)


def update_readme(table):
    with open("README.md", "r+", encoding="utf-8") as f:
        txt = f.read()
        start = "<!--TECH-STACK:START-->"
        end = "<!--TECH-STACK:END-->"
        block = f"{start}\n{table}\n{end}"
        if start in txt and end in txt:
            txt = re.sub(f"{start}.*?{end}", block, txt, flags=re.S)
        else:
            txt += f"\n\n## Recent Projects & Tech\n{block}\n"
        f.seek(0)
        f.write(txt)
        f.truncate()


def main():
    repos = [r for r in fetch(API) if not r["fork"]
             and r["visibility"] == "public"]
    # 只取最近更新的前 10 个
    rows = []
    for r in repos[:10]:
        rows.append(
            {"name": r["name"], "html_url": r["html_url"], "tech": detect_stack(r)})
    update_readme(build_table(rows))


if __name__ == "__main__":
    main()
