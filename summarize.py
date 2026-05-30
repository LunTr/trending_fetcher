import sys

sys.dont_write_bytecode = True

import json, os, glob, time, datetime
import fitz  # PyMuPDF
from openai import OpenAI

from Gtranslate import translate_large
from prompt_store import load_prompts, render_prompt

API_KEY_PATH = r"e:\DL\EssaysHere\API_KEY.json"
TODAY = datetime.datetime.now().strftime('%Y-%m-%d')
TARGET_DIR = os.path.join(os.getcwd(), TODAY)

README_CONTEXT_LIMIT_CHARS = 100_000
PROMPTS = load_prompts()

def call_chat(client, model, system_prompt, user_prompt, temperature=0.3, timeout=180):
    try:
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            timeout=timeout
        ).choices[0].message.content
    except Exception as e:
        print(e)
        return None

def read_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(e)
        return ""

def load_summary_models():
    with open(API_KEY_PATH, 'r', encoding='utf-8') as f:
        api_config = json.load(f)
    if isinstance(api_config, dict):
        return api_config.get("Summary_Models", [])
    return api_config


def get_model_name(api_conf):
    return api_conf.get("Model") or api_conf.get("Summary_Model")

def test_api_connection(api_conf):
    try:
        model_name = get_model_name(api_conf)
        if not model_name:
            print("[!] Summary 模型名缺失，跳过该配置。")
            return None, None
        client = OpenAI(
            api_key=api_conf["API_KEY"],
            base_url=api_conf["Base_URL"]
        )
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": PROMPTS["test_api_connection"]["user"]}],
            max_tokens=5,
            timeout=10
        )
        print(f"[*] 成功连接到模型: {model_name}")
        return client, model_name
    except Exception as e:
        print(e)
        return None, None

def get_working_client():
    apis = load_summary_models()
    if not apis:
        raise Exception("Summary_Models 为空或未配置。")
    for api_conf in apis:
        model_name = get_model_name(api_conf) or "<missing-model>"
        print(f"正在测试 API: {model_name} ...")
        client, model = test_api_connection(api_conf)
        if client:
            return client, model
    raise Exception("没有可用的API节点。")

def extract_text_from_pdf(pdf_path, max_pages=3):
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(min(max_pages, len(doc))):
            page = doc.load_page(page_num)
            text += page.get_text()
        return text
    except Exception as e:
        print(e)
        return ""

def summarize_paper(client, model, text):
    prompt_conf = PROMPTS["summarize_paper"]
    prompt = render_prompt(prompt_conf["user_template"], text=text)
    return call_chat(client, model, prompt_conf["system"], prompt, 0.3, 180)

def truncate_readme_text(text, max_chars=README_CONTEXT_LIMIT_CHARS):
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    if "\n" in truncated:
        truncated = truncated.rsplit("\n", 1)[0]
    return truncated + "\n..."

def translate_readme(client, model, text):
    limited_text = truncate_readme_text(text, README_CONTEXT_LIMIT_CHARS)
    prompt_conf = PROMPTS["translate_readme"]
    prompt = render_prompt(prompt_conf["user_template"], text=limited_text)
    return call_chat(client, model, prompt_conf["system"], prompt, 0.3, 180)

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
        readme_text = read_text_file(readme_path).strip()
        if not readme_text:
            continue

        translation = translate_readme(client, model, readme_text)
        if not translation or not translation.strip():
            print("  [!] 大模型翻译失败，切换 Google 翻译处理该文档。")
            try:
                limited_text = truncate_readme_text(readme_text, README_CONTEXT_LIMIT_CHARS)
                translation = translate_large(limited_text)
            except Exception as e:
                print(e)
                translation = None

        if translation and translation.strip():
            with open(zh_readme_path, "w", encoding="utf-8") as f:
                f.write(translation)
            print(f"  [+] 翻译保存成功: {zh_readme_path}")
        else:
            print("  [-] 翻译失败，未生成 README_zh.md。")
            
        time.sleep(2)

if __name__ == "__main__":
    process_files()