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

    # 添加空行（首项不加）
    if idx != 0:
        log("")

    # 去重逻辑
    merged_content = []
    seen_urls = set()

    with open(input_path, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]
    original_urls = [line for line in raw_lines if not line.startswith("#")]

    urls = []
    for url in original_urls:
        if url not in seen_urls:
            seen_urls.add(url)
            urls.append(url)
    duplicates_count = len(original_urls) - len(urls)

    # 修复首行空白问题
    comment_lines = [line for line in raw_lines if line.startswith("#")]
    new_txt_lines = []

    if comment_lines:
        new_txt_lines.extend(comment_lines)
        if urls:
            new_txt_lines.append("")  # 注释和 URL 之间插入空行
    if urls:
        new_txt_lines.extend(urls)

    new_txt_content = "\n".join(new_txt_lines) + "\n"

    with open(input_path, "r", encoding="utf-8") as f_check:
        old_txt_content = f_check.read()

    if new_txt_content != old_txt_content:
        with open(input_path, "w", encoding="utf-8") as f_out:
            f_out.write(new_txt_content)
        log(f"✏️ 已去重并更新源文件：{input_path}")
    else:
        log(f"✅ 无需更改源文件（无重复或内容一致）：{input_path}")

    log(f"📄 正在处理：{filename}")
    log(f"🔍 原始链接数：{len(original_urls)}，去重后：{len(urls)}，重复链接数：{duplicates_count}")

    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            merged_content.append(response.text)
        except Exception as e:
            log(f"⚠️ 无法读取 {url}：{e}")
            merged_content.append(f"# Error fetching {url}\n")

    new_content = "\n\n".join(merged_content)

    if not os.path.exists(output_path) or open(output_path, "r", encoding="utf-8").read() != new_content:
        with open(output_path, "w", encoding="utf-8") as out_f:
            out_f.write(new_content)
        log(f"✅ 已更新文件：{output_path}")
        has_changes = True
    else:
        log(f"🔄 无变更：{output_path}")

# Git 提交更新
if has_changes:
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPOSITORY")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

        subprocess.run(["git", "add", "Clash/*.list"], check=True)

        # ✅ 检查是否有实际变更再提交
        diff_result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_result.returncode != 0:
            subprocess.run(["git", "commit", "-m", "🤖 自动更新合并规则文件并去重源文件 [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            log("")  # 插入空行
            log("🚀 更改已提交并推送到远程仓库。")
        else:
            log("✅ 无需提交：git add 后无实际变更。")

    except subprocess.CalledProcessError as e:
        log(f"❌ Git 操作失败：{e}")
else:
    log("✅ 无需提交：没有任何更改。")
