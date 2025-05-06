import os
import subprocess
import requests

rules_dir = "rules"
output_dir = "Clash"

# 创建输出目录
os.makedirs(output_dir, exist_ok=True)

# 用于跟踪是否生成了新文件
has_changes = False

# 遍历 rules 目录下所有 .txt 文件
for filename in os.listdir(rules_dir):
    if filename.endswith(".txt"):
        input_path = os.path.join(rules_dir, filename)
        output_filename = os.path.splitext(filename)[0] + ".list"
        output_path = os.path.join(output_dir, output_filename)

        merged_content = []

        with open(input_path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

        for url in urls:
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                merged_content.append(response.text)
            except Exception as e:
                print(f"⚠️ 无法读取 {url}：{e}")
                merged_content.append(f"# Error fetching {url}\n")

        new_content = "\n\n".join(merged_content)

        # 写入并检查是否有变更
        if not os.path.exists(output_path) or open(output_path, "r", encoding="utf-8").read() != new_content:
            with open(output_path, "w", encoding="utf-8") as out_f:
                out_f.write(new_content)
            print(f"✅ 已更新文件：{output_path}")
            has_changes = True
        else:
            print(f"🔄 无变更：{output_path}")

# 如果有变更，执行 Git 提交和推送
if has_changes:
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "Clash/*.list"], check=True)
        subprocess.run(["git", "commit", "-m", "🤖 自动更新合并规则文件 [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("🚀 更改已提交并推送到远程仓库。")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作失败：{e}")
else:
    print("✅ 无需提交：没有任何更改。")
