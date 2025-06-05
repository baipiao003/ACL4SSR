import os
import subprocess
import requests
import re
from datetime import datetime

rules_dir = "rules"
output_dir = "Clash"
logs_dir = "logs"

os.makedirs(output_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

today = datetime.now().strftime("%Y-%m-%d")
log_file = os.path.join(logs_dir, f"merge-{today}.log")

has_changes = False
log_lines = []

def log(msg):
    print(msg)
    log_lines.append(msg)

log(f"📌 合并任务开始时间：{datetime.now().isoformat()}")
log("==========================================")

for filename in os.listdir(rules_dir):
    if filename.endswith(".txt"):
        input_path = os.path.join(rules_dir, filename)
        output_filename = os.path.splitext(filename)[0] + ".list"
        output_path = os.path.join(output_dir, output_filename)

        merged_content = []
        seen_urls = set()

        with open(input_path, "r", encoding="utf-8") as f:
            raw_lines = [line.strip() for line in f if line.strip()]

        # 原始链接排除注释
        original_urls = [line for line in raw_lines if not line.startswith("#")]

        # 去重链接
        urls = []
        for url in original_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                urls.append(url)

        duplicates_count = len(original_urls) - len(urls)

        # 生成新的 .txt 内容
        new_txt_lines = [line for line in raw_lines if line.startswith("#")]
        if urls:
            new_txt_lines.append("")
            new_txt_lines.extend(urls)
        new_txt_content = "\n".join(new_txt_lines) + "\n"

        # 检查是否需要写回 .txt
        with open(input_path, "r", encoding="utf-8") as f_check:
            old_txt_content = f_check.read()

        if new_txt_content != old_txt_content:
            with open(input_path, "w", encoding="utf-8") as f_out:
                f_out.write(new_txt_content)
            log(f"✏️ 已去重并更新源文件：{input_path}")
            has_changes = True
        else:
            log(f"✅ 无需更改源文件（无重复或内容一致）：{input_path}")

        log(f"\n📄 正在处理：{filename}")
        log(f"🔍 原始链接数：{len(original_urls)}，去重后：{len(urls)}，重复链接数：{duplicates_count}")

        # 合并下载内容
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

# Git 提交
if has_changes:
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPOSITORY")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)

        subprocess.run(["git", "add", "Clash/*.list", "rules/*.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "🤖 自动更新合并规则文件并去重源文件 [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)

        log("🚀 更改已提交并推送到远程仓库。")
    except subprocess.CalledProcessError as e:
        log(f"❌ Git 操作失败：{e}")
else:
    log("✅ 无需提交：没有任何更改。")

# 写入日志
with open(log_file, "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))

log(f"\n📝 日志已保存到 {log_file}")

# 日志清理：仅保留最近 10 条（按日志文件名日期排序）
pattern = re.compile(r"merge-(\d{4}-\d{2}-\d{2})\.log")
log_files = []

for f in os.listdir(logs_dir):
    match = pattern.fullmatch(f)
    if match:
        try:
            date_obj = datetime.strptime(match.group(1), "%Y-%m-%d")
            log_files.append((date_obj, os.path.join(logs_dir, f)))
        except ValueError:
            continue

log_files.sort(reverse=True)
for _, old_log in log_files[10:]:
    try:
        os.remove(old_log)
        log(f"🧹 已删除旧日志：{old_log}")
    except Exception as e:
        log(f"⚠️ 删除日志失败：{old_log}，原因：{e}")
