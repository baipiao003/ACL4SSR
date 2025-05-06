import os
import requests

# 定义文件夹路径
rules_dir = "rules"
output_dir = "Clash"

# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

# 遍历 rules 文件夹下所有 .txt 文件
for filename in os.listdir(rules_dir):
    if filename.endswith(".txt"):
        txt_path = os.path.join(rules_dir, filename)
        list_filename = os.path.splitext(filename)[0] + ".list"
        output_path = os.path.join(output_dir, list_filename)

        print(f"正在处理：{txt_path}")

        # 读取每个 txt 文件中的链接
        with open(txt_path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

        merged_blocks = []
        for url in urls:
            try:
                response = requests.get(url)
                response.raise_for_status()
                block = f"# 来源: {url}\n" + response.text.strip()
                merged_blocks.append(block)
            except Exception as e:
                print(f"  无法获取 {url}：{e}")

        # 拼接所有内容，以两个换行分隔块
        merged_content = "\n\n".join(merged_blocks)

        # 写入合并内容
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(merged_content)

        print(f"  已生成：{output_path}")

print("所有任务已完成。")
