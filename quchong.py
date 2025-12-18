import os
import sys
from pathlib import Path

def remove_duplicate_clash_rules(file_path):
    """
    去除Clash规则文件中的重复规则，直接在原文件上修改
    """
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分割成行
    lines = content.split('\n')
    
    # 分别存储不同类型的规则
    rules_by_type = {
        'DOMAIN': set(),
        'DOMAIN-SUFFIX': set(),
        'DOMAIN-KEYWORD': set(),
        'IP-CIDR': set(),
        'IP-ASN': set(),
        'OTHER': []  # 存储注释和其他内容
    }
    
    # 处理每一行
    output_lines = []
    
    for line in lines:
        line = line.rstrip()  # 只去除右边的空格，保持左边缩进
        
        # 空行直接保留
        if not line:
            output_lines.append(line)
            continue
        
        # 注释行（以#开头）直接保留
        if line.startswith('#'):
            rules_by_type['OTHER'].append(line)
            output_lines.append(line)
            continue
        
        # 尝试匹配规则类型
        rule_matched = False
        for rule_type in ['DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-ASN']:
            if line.startswith(rule_type):
                # 提取规则值（去掉类型和逗号后的参数）
                parts = line.split(',')
                if len(parts) >= 2:
                    rule_value = parts[1].strip()
                    # 如果还有更多参数，保留原始格式
                    rule_full = line
                else:
                    # 如果没有逗号，可能是格式错误，按原样处理
                    rule_value = line[len(rule_type):].strip()
                    rule_full = line
                
                # 检查是否重复（基于规则值）
                if rule_value not in rules_by_type[rule_type]:
                    rules_by_type[rule_type].add(rule_value)
                    output_lines.append(rule_full)
                else:
                    # 重复规则，跳过
                    print(f"  ⚠️ 跳过重复规则: {line[:80]}{'...' if len(line) > 80 else ''}")
                rule_matched = True
                break
        
        if not rule_matched:
            # 未知类型的行，直接保留
            rules_by_type['OTHER'].append(line)
            output_lines.append(line)
    
    # 计算统计信息
    total_input_rules = sum(1 for line in lines if line and not line.startswith('#') and 
                           any(line.startswith(rt) for rt in ['DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-ASN']))
    total_output_rules = sum(len(v) for k, v in rules_by_type.items() if k != 'OTHER')
    removed_count = total_input_rules - total_output_rules
    
    # 写入去重后的内容到原文件
    with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(output_lines))
    
    return {
        'file_name': os.path.basename(file_path),
        'input_rules': total_input_rules,
        'output_rules': total_output_rules,
        'removed': removed_count,
        'rules_by_type': rules_by_type
    }

def process_clash_folder(folder_path):
    """
    处理Clash文件夹中的所有.list文件
    """
    folder_path = Path(folder_path)
    
    if not folder_path.exists():
        print(f"❌ 错误: 文件夹 '{folder_path}' 不存在")
        return None
    
    # 查找所有.list文件
    list_files = list(folder_path.glob("*.list"))
    
    if not list_files:
        print(f"ℹ️ 在 '{folder_path}' 中没有找到.list文件")
        return None
    
    print(f"📁 找到 {len(list_files)} 个规则文件:")
    for file in list_files:
        print(f"  • {file.name}")
    print()
    
    results = []
    total_removed = 0
    
    # 处理每个文件
    for list_file in list_files:
        print(f"\n🔧 处理文件: {list_file.name}")
        
        # 处理文件（直接在原文件上修改）
        result = remove_duplicate_clash_rules(list_file)
        results.append(result)
        
        if result['removed'] > 0:
            print(f"  ✅ 完成! 移除了 {result['removed']} 条重复规则")
            print(f"    原始: {result['input_rules']} 条 → 现在: {result['output_rules']} 条")
            total_removed += result['removed']
        else:
            print(f"  ℹ️  没有发现重复规则")
    
    return {
        'results': results,
        'total_removed': total_removed,
        'processed_files': len(list_files)
    }

def generate_report(process_result):
    """
    生成处理报告
    """
    if not process_result:
        return
    
    results = process_result['results']
    total_removed = process_result['total_removed']
    
    print("\n" + "="*60)
    print("📊 处理完成! 汇总报告:")
    print("="*60)
    
    for result in results:
        status = "✅ 已清理" if result['removed'] > 0 else "ℹ️  无重复"
        print(f"{result['file_name']:30} {status:15} 规则: {result['output_rules']:4} 条 (移除 {result['removed']:3} 条)")
    
    print("="*60)
    print(f"📈 总计: 处理了 {len(results)} 个文件，移除了 {total_removed} 条重复规则")
    
    # 按规则类型统计
    print("\n📋 规则类型统计:")
    type_totals = {}
    for result in results:
        for rule_type, rule_set in result['rules_by_type'].items():
            if rule_type != 'OTHER':
                count = len(rule_set)
                type_totals[rule_type] = type_totals.get(rule_type, 0) + count
    
    for rule_type, count in sorted(type_totals.items()):
        print(f"  {rule_type:15} {count:5} 条")

def main():
    """
    主函数：处理Clash文件夹中的规则文件
    """
    print("="*60)
    print("🛠️  Clash规则去重脚本 - quchong.py")
    print("="*60)
    
    # 获取当前目录（脚本所在目录）
    current_dir = Path.cwd()
    print(f"📂 当前工作目录: {current_dir}")
    
    # 首先检查当前目录是否有Clash文件夹
    possible_names = ['Clash', 'clash', 'CLASH']
    clash_folder = None
    
    for folder_name in possible_names:
        test_path = current_dir / folder_name
        if test_path.exists() and test_path.is_dir():
            clash_folder = test_path
            print(f"✅ 找到文件夹: {clash_folder}")
            break
    
    # 如果通过命令行参数指定了路径
    if len(sys.argv) > 1:
        custom_path = Path(sys.argv[1])
        if not custom_path.is_absolute():
            custom_path = current_dir / custom_path
            
        custom_path = custom_path.resolve()
        
        if custom_path.exists() and custom_path.is_dir():
            clash_folder = custom_path
            print(f"✅ 使用指定的文件夹: {clash_folder}")
        else:
            print(f"❌ 错误: 指定的路径不存在或不是文件夹: {custom_path}")
            print("\n当前目录结构:")
            for item in sorted(current_dir.iterdir()):
                if item.is_dir():
                    print(f"  📁 {item.name}/")
                else:
                    print(f"  📄 {item.name}")
            sys.exit(1)
    
    if not clash_folder:
        print("❌ 错误: 未找到Clash文件夹")
        print("\n当前目录结构:")
        for item in sorted(current_dir.iterdir()):
            if item.is_dir():
                print(f"  📁 {item.name}/")
            else:
                print(f"  📄 {item.name}")
        
        print("\n请执行以下操作之一:")
        print("1. 确保Clash文件夹存在于当前目录")
        print("2. 指定Clash文件夹路径: python quchong.py Clash")
        print("3. 指定Clash文件夹路径: python quchong.py ./Clash")
        sys.exit(1)
    
    print(f"🎯 目标文件夹: {clash_folder}")
    print("⚠️  注意: 将直接在原文件上修改，不创建备份")
    print("-" * 60)
    
    # 交互模式下的确认
    if len(sys.argv) <= 1:  # 如果不是通过命令行指定路径
        response = input("❓ 确定要继续吗？(y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("操作已取消")
            return
    
    # 处理文件夹
    process_result = process_clash_folder(clash_folder)
    
    # 生成报告
    if process_result:
        generate_report(process_result)
        print(f"\n✅ 所有文件处理完成！")
        print(f"📁 文件位置: {clash_folder}")
    else:
        print(f"⚠️  没有处理任何文件")

if __name__ == "__main__":
    main()
