import os
import sys
import requests
import glob
from urllib.parse import urlparse

def download_list(url):
    """下载单个规则列表并返回内容"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"下载失败 {url}: {e}")
        return None

def process_txt_file(txt_path, clash_dir):
    """处理单个txt文件"""
    # 获取文件名（不含扩展名）
    filename = os.path.splitext(os.path.basename(txt_path))[0]
    output_path = os.path.join(clash_dir, f"{filename}.list")
    
    print(f"\n处理文件: {txt_path}")
    print(f"输出文件: {output_path}")
    
    # 读取txt文件中的链接
    with open(txt_path, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    print(f"找到 {len(urls)} 个规则链接")
    
    merged_rules = []
    seen = set()
    
    # 处理每个链接
    for idx, url in enumerate(urls, 1):
        print(f"  [{idx}/{len(urls)}] 处理: {url}")
        content = download_list(url)
        if content:
            # 按行分割，去重
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and line not in seen:
                    seen.add(line)
                    merged_rules.append(line)
    
    # 保存合并后的规则
    with open(output_path, 'w', encoding='utf-8') as f:
        # 写入文件头部信息
        f.write(f"# {filename}.list - 自动生成\n")
        f.write(f"# 来源: {os.path.basename(txt_path)}\n")
        f.write(f"# 规则数: {len(merged_rules)}\n\n")
        
        for rule in merged_rules:
            f.write(rule + "\n")
    
    print(f"  完成！共 {len(merged_rules)} 条规则")
    return len(merged_rules)

def main():
    # 路径配置
    rules_dir = "rules"
    clash_dir = "Clash"
    
    # 确保输出目录存在
    os.makedirs(clash_dir, exist_ok=True)
    
    # 查找rules文件夹下所有的txt文件
    txt_files = glob.glob(os.path.join(rules_dir, "*.txt"))
    
    if not txt_files:
        print(f"在 {rules_dir} 文件夹下未找到任何 .txt 文件")
        sys.exit(1)
    
    print(f"找到 {len(txt_files)} 个txt文件:")
    for i, file in enumerate(txt_files, 1):
        print(f"  {i}. {os.path.basename(file)}")
    
    total_files = len(txt_files)
    successful_files = 0
    
    # 处理每个txt文件
    for idx, txt_file in enumerate(txt_files, 1):
        print(f"\n{'='*50}")
        print(f"处理第 {idx}/{total_files} 个文件")
        
        try:
            rule_count = process_txt_file(txt_file, clash_dir)
            if rule_count > 0:
                successful_files += 1
        except Exception as e:
            print(f"处理文件 {txt_file} 时出错: {e}")
    
    print(f"\n{'='*50}")
    print("处理完成！")
    print(f"成功处理: {successful_files}/{total_files} 个文件")
    print(f"输出目录: {clash_dir}")
    
    # 显示生成的list文件列表
    list_files = glob.glob(os.path.join(clash_dir, "*.list"))
    if list_files:
        print(f"\n生成的list文件:")
        for file in list_files:
            file_size = os.path.getsize(file)
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                rule_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]
                print(f"  {os.path.basename(file)}: {len(rule_lines)} 条规则 ({file_size} 字节)")

if __name__ == "__main__":
    main()
