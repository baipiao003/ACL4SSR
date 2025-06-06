import os
import subprocess
import requests
from datetime import datetime

rules_dir = "rules"
output_dir = "Clash"

os.makedirs(output_dir, exist_ok=True)

def log(message: str):
    print(message)

log(f"📌 合并任务开始时间：{datetime.now().isoformat()}")

txt_files = sorted([f for f in os.listdir(rules_dir) if f.endswith(".txt")])
has_changes = False

for idx, filename in enumerate(txt_files):
    input_path = os.path.join(rules_dir, filename)
    output_filename = os.path.splitext(filename)[0] + ".list"
    output_path = os.path.join(output_dir, output_filename)

    if idx != 0:
        log("")

    # 读取所有行，保留注释
    with open(input_path, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    comment_lines = [line for line in raw_lines if line.startswith("#")]
    url_lines = [line for line in raw_lines if not line.startswith("#")]

    # 去重链接
    seen = set()
    deduped_urls = []
    for url in url_lines:
        if url not in seen:
            seen.add(url)
            deduped_urls.append(url)

    duplicates_count = len(url_lines) - len(deduped_urls)

    # 如果有重复，保存覆盖原文件
    if duplicates_count > 0:
        new_lines = comment_lines + ([""] if comment_lines and deduped_urls else []) + deduped_urls
        with open(input_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(new_lines) + "\n")
        log(f"✏️ 已去重并覆盖原文件：{input_path}")
    else:
        log(f"✅ 无需修改（无重复）：{input_path}")

    log(f"📄 正在处理：{filename}")
    log(f"🔍 原始链接数：{len(url_lines)}，去重后：{len(deduped_urls)}，重复链接数：{duplicates_count}")

    # 下载合并 .list 内容
    merged_content = []
    for url in deduped_urls:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            merged_content.append(resp.text)
        except Exception as e:
            log(f"⚠️ 无法读取 {url}：{e}")
            merged_content.append(f"# Error fetching {url}\n")

    final_content = "\n\n".join(merged_content)

    # 写入输出文件（如果变更）
    if not os.path.exists(output_path) or open(output_path, "r", encoding="utf-8").read() != final_content:
        with open(output_path, "w", encoding="utf-8") as f_out:
            f_out.write(final_content)
        log(f"✅ 已更新文件：{output_path}")
        has_changes = True
    else:
        log(f"🔄 无变更：{output_path}")

# Git 自动提交
if has_changes:
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPOSITORY")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

        subprocess.run(["git", "add", "Clash/*.list"], check=True)

        # 有改动再提交
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", "🤖 自动更新合并规则文件并去重源文件 [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            log("")
            log("🚀 更改已提交并推送到远程仓库。")
        else:
            log("✅ 无需提交：没有实际更改。")
    except subprocess.CalledProcessError as e:
        log(f"❌ Git 操作失败：{e}")
else:
    log("✅ 无需提交：没有任何更改。")
