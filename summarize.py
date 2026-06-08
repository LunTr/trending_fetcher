import sys

sys.dont_write_bytecode = True

import json, os, glob, time, datetime
import fitz  # PyMuPDF
from openai import OpenAI

from Gtranslate import translate_large
from prompt_store import load_prompts, render_prompt

DATA_ROOT = os.path.abspath(
    os.environ.get("TRENDING_FETCHER_DATA_DIR")
    or os.path.join(os.path.dirname(__file__), "..")
)
API_KEY_PATH = os.environ.get("TRENDING_FETCHER_API_KEY") or os.path.join(DATA_ROOT, "API_KEY.json")
TODAY = datetime.datetime.now().strftime('%Y-%m-%d')
TARGET_DIR = os.path.join(DATA_ROOT, TODAY)

README_CONTEXT_LIMIT_CHARS = 100_000
PROMPTS = load_prompts()

def emit(reporter, event, **payload):
    if reporter:
        reporter({"event": event, **payload})

def log(reporter, message, **payload):
    print(message)
    emit(reporter, "log", message=message, **payload)

def configure_runtime(data_root=None, date_str=None):
    global DATA_ROOT, API_KEY_PATH, TODAY, TARGET_DIR
    if data_root:
        DATA_ROOT = os.path.abspath(data_root)
    os.makedirs(DATA_ROOT, exist_ok=True)
    API_KEY_PATH = os.environ.get("TRENDING_FETCHER_API_KEY") or os.path.join(DATA_ROOT, "API_KEY.json")
    if date_str:
        TODAY = date_str
    TARGET_DIR = os.path.join(DATA_ROOT, TODAY)

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

def test_api_connection(api_conf, reporter=None):
    try:
        model_name = get_model_name(api_conf)
        if not model_name:
            log(reporter, "[!] Summary 模型名缺失，跳过该配置。", stage="model-test", level="error")
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
        log(reporter, f"[*] 成功连接到模型: {model_name}", stage="model-test", model=model_name)
        return client, model_name
    except Exception as e:
        log(reporter, str(e), stage="model-test", level="error")
        return None, None

def get_working_client(reporter=None):
    apis = load_summary_models()
    if not apis:
        raise Exception("Summary_Models 为空或未配置。")
    for api_conf in apis:
        model_name = get_model_name(api_conf) or "<missing-model>"
        log(reporter, f"正在测试 API: {model_name} ...", stage="model-test", model=model_name)
        client, model = test_api_connection(api_conf, reporter=reporter)
        if client:
            return client, model
    raise Exception("没有可用的API节点。")

def extract_text_from_pdf(pdf_path, max_pages=None):
    text = ""
    try:
        doc = fitz.open(pdf_path)
        page_limit = len(doc) if max_pages is None else min(max_pages, len(doc))
        for page_num in range(page_limit):
            page = doc.load_page(page_num)
            text += page.get_text()
        return text
    except Exception as e:
        print(e)
        return ""

def summarize_paper(client, model, text):
    abstract_conf = PROMPTS["summarize_paper_abstract"]
    abstract_prompt = render_prompt(abstract_conf["user_template"], text=text)
    abstract_translation = call_chat(client, model, abstract_conf["system"], abstract_prompt, 0.3, 180)
    if not abstract_translation or not abstract_translation.strip():
        return None

    structured_conf = PROMPTS["summarize_paper_structured"]
    structured_prompt = render_prompt(
        structured_conf["user_template"],
        text=text,
        abstract_translation=abstract_translation.strip()
    )
    structured_summary = call_chat(client, model, structured_conf["system"], structured_prompt, 0.3, 180)
    if not structured_summary or not structured_summary.strip():
        return None

    return (
        "# 摘要译文\n"
        f"{abstract_translation.strip()}\n\n"
        "# 结构化摘要\n"
        f"{structured_summary.strip()}"
    )

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

def build_today_kb(reporter=None):
    try:
        import createbase
        kb_dir = os.path.join(DATA_ROOT, "kb_store")
        log(reporter, "Starting offline KB build after summarize...", stage="kb-build", source_dir=TARGET_DIR)
        createbase.build_kb(source_dir=TARGET_DIR, kb_dir=kb_dir, api_key_path=API_KEY_PATH, reporter=reporter)
    except Exception as e:
        log(reporter, f"[!] KB build skipped: {e}", stage="kb-build", level="error")

def process_files(data_root=None, date_str=None, reporter=None, build_index=False):
    configure_runtime(data_root=data_root, date_str=date_str)
    if not os.path.exists(TARGET_DIR):
        log(reporter, f"找不到今日目录: {TARGET_DIR}，请确保 main.py 正常运行并下载了当天的内容。", stage="summarize", level="error")
        return
        
    client, model = get_working_client(reporter=reporter)
    
    log(reporter, "\n--- 开始分析 PDF 论文 ---", stage="pdf-summary")
    pdf_files = glob.glob(os.path.join(TARGET_DIR, "**", "*.pdf"), recursive=True)
    if not pdf_files:
        log(reporter, "没有找到 PDF 文件。", stage="pdf-summary")
    emit(reporter, "queue", stage="pdf-summary", current=0, total=len(pdf_files))
    
    pdf_done = 0
    pdf_skipped = 0
    pdf_failed = 0
    for idx, pdf_path in enumerate(pdf_files, 1):
        md_path = pdf_path.replace(".pdf", "_summary.md")
        emit(reporter, "queue", stage="pdf-summary", current=idx, total=len(pdf_files), file_name=os.path.basename(pdf_path), file_path=pdf_path)
        
        if os.path.exists(md_path):
            pdf_skipped += 1
            log(reporter, f"[*] 已存在摘要，跳过: {os.path.basename(pdf_path)}", stage="pdf-summary", file_path=pdf_path)
            continue
            
        log(reporter, f"\n[+] 正在提取并总结论文: {os.path.basename(pdf_path)}", stage="pdf-summary", file_path=pdf_path)
        paper_text = extract_text_from_pdf(pdf_path)
        
        if not paper_text.strip():
            pdf_failed += 1
            log(reporter, "  [-] 无法提取文本或文件为空。", stage="pdf-summary", file_path=pdf_path, level="error")
            continue
            
        summary = None
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            summary = summarize_paper(client, model, paper_text)
            if summary:
                break
            log(reporter, f"  [!] 第 {attempt}/{max_attempts} 次总结失败，重新连接可用模型后重试...", stage="pdf-summary", attempt=attempt, max_attempts=max_attempts)
            try:
                client, model = get_working_client(reporter=reporter)
            except Exception as e:
                log(reporter, f"  [-] 无可用模型，终止重试: {e}", stage="pdf-summary", level="error")
                break
            time.sleep(2)
        
        if summary:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(summary)
            pdf_done += 1
            log(reporter, f"  [+] 摘要保存成功: {md_path}", stage="pdf-summary", file_path=md_path)
        else:
            pdf_failed += 1
            log(reporter, f"  [-] 总结失败，未生成: {md_path}", stage="pdf-summary", file_path=md_path, level="error")
            
        time.sleep(2)

    emit(reporter, "stats", pdf_done=pdf_done, pdf_skipped=pdf_skipped, pdf_failed=pdf_failed)
    log(reporter, "\n--- 开始翻译 GitHub README ---", stage="readme-translate")
    readme_files = glob.glob(os.path.join(TARGET_DIR, "GitHub", "**", "README.md"), recursive=True)
    if not readme_files:
        log(reporter, "今日 GitHub 目录下没有找到任何 README.md 文件。", stage="readme-translate")
    emit(reporter, "queue", stage="readme-translate", current=0, total=len(readme_files))
        
    readme_done = 0
    readme_skipped = 0
    readme_failed = 0
    for idx, readme_path in enumerate(readme_files, 1):
        zh_readme_path = os.path.join(os.path.dirname(readme_path), "README_zh.md")
        emit(reporter, "queue", stage="readme-translate", current=idx, total=len(readme_files), file_name=os.path.basename(os.path.dirname(readme_path)), file_path=readme_path)
        
        if os.path.exists(zh_readme_path):
            readme_skipped += 1
            log(reporter, f"[*] 已存在中文翻译，跳过: {os.path.basename(os.path.dirname(readme_path))}/README_zh.md", stage="readme-translate", file_path=zh_readme_path)
            continue
            
        log(reporter, f"\n[+] 正在翻译 README: {os.path.basename(os.path.dirname(readme_path))}", stage="readme-translate", file_path=readme_path)
        readme_text = read_text_file(readme_path).strip()
        if not readme_text:
            continue

        translation = translate_readme(client, model, readme_text)
        if not translation or not translation.strip():
            log(reporter, "  [!] 大模型翻译失败，切换 Google 翻译处理该文档。", stage="readme-translate")
            try:
                limited_text = truncate_readme_text(readme_text, README_CONTEXT_LIMIT_CHARS)
                translation = translate_large(limited_text)
            except Exception as e:
                print(e)
                translation = None

        if translation and translation.strip():
            with open(zh_readme_path, "w", encoding="utf-8") as f:
                f.write(translation)
            readme_done += 1
            log(reporter, f"  [+] 翻译保存成功: {zh_readme_path}", stage="readme-translate", file_path=zh_readme_path)
        else:
            readme_failed += 1
            log(reporter, "  [-] 翻译失败，未生成 README_zh.md。", stage="readme-translate", level="error")
            
        time.sleep(2)

    emit(reporter, "stats", readme_done=readme_done, readme_skipped=readme_skipped, readme_failed=readme_failed)
    if build_index:
        build_today_kb(reporter=reporter)

if __name__ == "__main__":
    process_files()
