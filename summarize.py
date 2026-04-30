import json
import os
import glob
import fitz  # PyMuPDF
from openai import OpenAI
import time
import datetime

API_KEY_PATH = r"e:\DL\EssaysHere\API_KEY.json"
TODAY = datetime.datetime.now().strftime('%Y-%m-%d')
# 使用执行时的当前工作目录
BASE_DIR = os.getcwd()
TARGET_DIR = os.path.join(BASE_DIR, TODAY)

def load_apis():
    with open(API_KEY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_api_connection(api_conf):
    """测试API是否可用"""
    try:
        client = OpenAI(
            api_key=api_conf["API_KEY"],
            base_url=api_conf["Base_URL"]
        )
        # 发送一个极简请求测试连通性
        response = client.chat.completions.create(
            model=api_conf["Model"],
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5,
            timeout=10
        )
        print(f"[*] 成功连接到模型: {api_conf['Model']}")
        return client, api_conf["Model"]
    except Exception as e:
        print(f"[!] 模型 {api_conf['Model']} 连接失败: {e}")
        return None, None

def get_working_client():
    apis = load_apis()
    for api_conf in apis:
        print(f"正在测试 API: {api_conf['Model']} ...")
        client, model = test_api_connection(api_conf)
        if client:
            return client, model
    raise Exception("没有可用的API节点。")

def extract_text_from_pdf(pdf_path, max_pages=3):
    """提取PDF前几页的文本（避免Token超限）"""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        # 通常摘要和Conclusion都在前页和末页，这里我们只取前3页读取Abstract和Introduction
        for page_num in range(min(max_pages, len(doc))):
            page = doc.load_page(page_num)
            text += page.get_text()
        return text
    except Exception as e:
        print(f"读取 PDF 出错 ({pdf_path}): {e}")
        return ""

def summarize_paper(client, model, text):
    """请求模型生成中文Markdown摘要"""
    prompt = f"""
    你是一位 INTJ 型人格的AI研究员，阅读以下学术论文的片段（通常包含标题、摘要和引言），完整翻译Abstract，并生成一份结构化的中文摘要。沟通直接、简洁、结构化，避免空泛鼓励和情绪化，尽量少使用关联词。
    
    请使用Markdown格式，包含以下必填内容：
    1. **论文核心目标/问题**：(解决什么问题)
    2. **主要创新点/方法**：(提出了什么新方法)
    3. **潜在价值与应用场景**：(有什么用)
    
    论文文本如下：
    {text}  # 截断以确保不超过上下文长度
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位专业的AI科研人员。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            timeout=180
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[!] 摘要生成失败: {e}")
        return None

def translate_readme(client, model, text):
    """请求模型翻译 README.md 为中文"""
    prompt = f"""
    将以下开源项目的 README 翻译成中文。请保持原有的 Markdown 格式。
    以下为原文：
    {text}
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位专业的开源项目翻译员。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            timeout=180
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[!] 翻译失败: {e}")
        return None

def process_files():
    if not os.path.exists(TARGET_DIR):
        print(f"找不到今日目录: {TARGET_DIR}，请确保 main.py 正常运行并下载了当天的内容。")
        return
        
    client, model = get_working_client()
    
    print("\n--- 开始分析 PDF 论文 ---")
    pdf_files = glob.glob(os.path.join(TARGET_DIR, "**", "*.pdf"), recursive=True)
    if not pdf_files:
        print("没有找到 PDF 文件。")
    
    for pdf_path in pdf_files:
        md_path = pdf_path.replace(".pdf", "_summary.md")
        
        if os.path.exists(md_path):
            print(f"[*] 已存在摘要，跳过: {os.path.basename(pdf_path)}")
            continue
            
        print(f"\n[+] 正在提取并总结论文: {os.path.basename(pdf_path)}")
        paper_text = extract_text_from_pdf(pdf_path)
        
        if not paper_text.strip():
            print("  [-] 无法提取文本或文件为空。")
            continue
            
        summary = summarize_paper(client, model, paper_text)
        
        if summary:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"  [+] 摘要保存成功: {md_path}")
            
        time.sleep(2)
        
    print("\n--- 开始翻译 GitHub README ---")
    readme_files = glob.glob(os.path.join(TARGET_DIR, "GitHub", "**", "README.md"), recursive=True)
    if not readme_files:
        print("今日 GitHub 目录下没有找到任何 README.md 文件。")
        
    for readme_path in readme_files:
        zh_readme_path = os.path.join(os.path.dirname(readme_path), "README_zh.md")
        
        if os.path.exists(zh_readme_path):
            print(f"[*] 已存在中文翻译，跳过: {os.path.basename(os.path.dirname(readme_path))}/README_zh.md")
            continue
            
        print(f"\n[+] 正在翻译 README: {os.path.basename(os.path.dirname(readme_path))}")
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_text = f.read()
                
            if not readme_text.strip():
                continue
                
            translation = translate_readme(client, model, readme_text)
            if translation:
                with open(zh_readme_path, "w", encoding="utf-8") as f:
                    f.write(translation)
                print(f"  [+] 翻译保存成功: {zh_readme_path}")
        except Exception as e:
            print(f"  [-] 读取/翻译 README 时出错: {e}")
            
        time.sleep(2)

if __name__ == "__main__":
    process_files()