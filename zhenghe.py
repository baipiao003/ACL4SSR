import os
import subprocess
import requests
from datetime import datetime

# 📁 规则源目录 和 输出目录
rules_dir = "rules"
output_dir = "Clash"

# ⛏️ 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

def log(message: str):
    print(message)

log(f"📌 合并任务开始时间：{datetime.now().isoformat()}")

# 📄 获取所有 .txt 文件（按名称排序）
txt_files = sorted([f for f in os.listdir(rules_dir) if f.endswith(".txt")])
has_changes = False

for idx, filename in enumerate(txt_files):
    input_path = os.path.join(rules_dir, filename)
    output_filename = os.path.splitext(filename)[0] + ".list"
    output_path = os.path.join(output_dir, output_filename)

    if idx != 0:
        log("")  # 美观换行

    # 📥 读取原始行并去除空行
    with open(input_path, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    # 🔍 拆分注释和 URL
    comment_lines = [line for line in raw_lines if line.startswith("#")]
    url_lines = [line for line in raw_lines if not line.startswith("#")]

    # 🧹 去重链接
    seen = set()
    deduped_urls = []
    for url in url_lines:
        if url not in seen:
            seen.add(url)
            deduped_urls.append(url)

    duplicates_count = len(url_lines) - len(deduped_urls)

    # 🛠 构造去重后的新内容
    new_lines = comment_lines + ([""] if comment_lines and deduped_urls else []) + deduped_urls
    new_txt_content = "\n".join(new_lines) + "\n"

    log(f"📄 正在处理：{filename}")
    if duplicates_count > 0:
        log(f"🧹 去除重复链接，数量：{duplicates_count}")
    else:
        log(f"✅ 链接无重复。")
    log(f"🔍 原始链接数：{len(url_lines)}，去重后：{len(deduped_urls)}")

    # ✏️ 仅在内容变更时写入 .txt 文件
    with open(input_path, "r", encoding="utf-8") as f_in:
        original_txt_content = f_in.read()

    if original_txt_content != new_txt_content:
        with open(input_path, "w", encoding="utf-8", newline="\n") as f_out:
            f_out.write(new_txt_content)
        subprocess.run(["git", "add", input_path], check=True)
        log(f"✅ 已更新源文件：{input_path}")
        has_changes = True
    else:
        log(f"🔄 无需更新源文件：{input_path}")

    # 🌐 下载并合并所有 URL 内容
    merged_content = []
    for url in deduped_urls:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            merged_content.append(resp.text)
        except Exception as e:
            log(f"⚠️ 无法读取 {url}：{e}")
            merged_content.append(f"# Error fetching {url}\n")
            
    # 改这里，改为一个换行分隔
    final_content = "\n".join(merged_content)

    # 📤 写入输出 .list 文件（仅在内容变更时写入），规范换行符和空白差异避免误判
    final_normalized = final_content.strip().replace("\r\n", "\n").replace("\r", "\n")

    existing_normalized = ""
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            existing_normalized = f.read().strip().replace("\r\n", "\n").replace("\r", "\n")

    if final_normalized != existing_normalized:
        with open(output_path, "w", encoding="utf-8", newline="\n") as f_out:
            f_out.write(final_content)
        log(f"✅ 已更新文件：{output_path}")
        has_changes = True
        subprocess.run(["git", "add", output_path], check=True)
    else:
        log(f"🔄 无需更新：{output_path}")

# 🧾 Git 自动提交（如有文件更新）
if has_changes:
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPOSITORY")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", "🤖 自动更新合并规则文件并去重源文件 [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            log("")  # 美观换行
            log("🚀 更改已提交并推送到远程仓库。")
        else:
            log("")  # 美观换行
            log("✅ 无需提交：没有实际更改。")
    except subprocess.CalledProcessError as e:
        log(f"❌ Git 操作失败：{e}")
else:
    log("")  # 美观换行
    log("✅ 无需提交：没有任何更改。")
