import json, os, glob, re, time, datetime, urllib.request
import fitz  # PyMuPDF
import requests
import urllib3
from openai import OpenAI

API_KEY_PATH = r"e:\DL\EssaysHere\API_KEY.json"
TODAY = datetime.datetime.now().strftime('%Y-%m-%d')
TARGET_DIR = os.path.join(os.getcwd(), TODAY)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
SYSTEM_PROXIES = urllib.request.getproxies()

HTTP_SESSION = requests.Session()
if SYSTEM_PROXIES:
    HTTP_SESSION.proxies.update(SYSTEM_PROXIES)
HTTP_SESSION.verify = False
HTTP_SESSION.trust_env = True
HTTP_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
})

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

def load_apis():
    with open(API_KEY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_api_connection(api_conf):
    try:
        client = OpenAI(
            api_key=api_conf["API_KEY"],
            base_url=api_conf["Base_URL"]
        )
        response = client.chat.completions.create(
            model=api_conf["Model"],
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=5,
            timeout=10
        )
        print(f"[*] 成功连接到模型: {api_conf['Model']}")
        return client, api_conf["Model"]
    except Exception as e:
        print(e)
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
    prompt = (
        "你是一位 INTJ 型人格的AI研究员，阅读以下学术论文，完整翻译Abstract，并生成结构化中文摘要。\n"
        "沟通直接、简洁，避免空泛鼓励和情绪化，不要过多使用关联词。\n\n"
        "请使用Markdown格式，包含以下必填内容：\n"
        "1. **论文核心目标/问题**：(解决什么问题)\n"
        "2. **主要创新点/方法**：(提出了什么新方法)\n"
        "3. **潜在价值与应用场景**：(有什么用)\n\n"
        f"论文文本如下：\n{text}"
    )
    return call_chat(client, model, "你是一位专业的AI科研人员。", prompt, 0.3, 180)

def translate_readme(client, model, text):
    prompt = "将以下开源项目的 README 翻译成中文，保持原有 Markdown 格式。\n原文：\n" + text
    return call_chat(client, model, "你是一位专业的开源项目翻译员。", prompt, 0.3, 180)

def truncate_text(text, max_chars=1200):
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    if "\n" in truncated:
        truncated = truncated.rsplit("\n", 1)[0]
    return truncated + "\n..."

def parse_title_and_arxiv_id(file_path):
    base_name = os.path.basename(file_path)
    name = base_name.replace("_summary.md", "").replace(".pdf", "")
    if name == base_name:
        name = os.path.splitext(base_name)[0]

    match = re.search(r"_(\d{4}\.\d{4,5})(v\d+)?$", name)
    if match:
        arxiv_id = f"{match.group(1)}{match.group(2) or ''}"
        title = name[:match.start()]
        title = title[:-1] if title.endswith("_") else title
        return title, arxiv_id
    return name, None

def extract_json_block(text):
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n|\n```$", "", text.strip(), flags=re.S)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

def collect_hf_candidates():
    hf_dir = os.path.join(TARGET_DIR, "HuggingFace")
    if not os.path.exists(hf_dir):
        return []

    summary_paths = sorted(glob.glob(os.path.join(hf_dir, "**", "*_summary.md"), recursive=True))
    candidates = []
    for idx, summary_path in enumerate(summary_paths, 1):
        summary_text = read_text_file(summary_path).strip()
        if not summary_text:
            continue

        title, arxiv_id = parse_title_and_arxiv_id(summary_path)
        candidates.append({
            "id": str(idx),
            "title": title,
            "summary": summary_text,
            "summary_path": summary_path,
            "arxiv_id": arxiv_id
        })
    return candidates

def choose_by_keyword(candidates):
    keywords = [
        "llm", "large language model", "language model", "gpt", "chatgpt",
        "transformer", "instruction", "prompt", "alignment", "rlhf",
        "in-context", "reasoning", "agent", "tool", "retrieval"
    ]
    best = None
    best_score = -1
    for c in candidates:
        text = f"{c['title']}\n{c['summary']}".lower()
        score = sum(text.count(k) for k in keywords)
        if score > best_score:
            best_score = score
            best = c
    return best

def choose_best_llm_paper(client, model, candidates):
    if not candidates:
        return None, ""

    items = []
    for c in candidates:
        short_summary = truncate_text(c["summary"], 1200)
        items.append(
            f"ID: {c['id']}\nTitle: {c['title']}\nSummary:\n{short_summary}\n"
        )

    prompt = (
        "你需要从候选中选出在大语言模型(LLM)方面最有意思、最有潜力的一篇。\n"
        "要求：\n"
        "1) 必须从候选 ID 中选一个。\n"
        "2) 如果都不是 LLM 方向，也要选最接近的一篇。\n"
        "3) 只输出 JSON，不要多余文字。\n"
        "输出格式: {\"id\":\"...\", \"reason\":\"...\"}\n\n"
        "候选：\n" + "\n".join(items)
    )

    raw = call_chat(
        client,
        model,
        "你是一位资深AI研究员，擅长筛选最有潜力或者你觉得有意思的LLM论文。",
        prompt,
        0.2,
        180
    )
    if not raw:
        return choose_by_keyword(candidates), ""

    selection = extract_json_block(raw)
    if not selection:
        print("无法解析模型输出，改用关键词匹配选择。")
        return choose_by_keyword(candidates), ""

    selected_id = str(selection.get("id", "")).strip()
    reason = str(selection.get("reason", "")).strip()
    selected = next((c for c in candidates if c["id"] == selected_id), None)
    if not selected:
        print("模型选择的 ID 无效，改用关键词匹配选择。")
        return choose_by_keyword(candidates), reason
    return selected, reason

def download_arxiv_source(arxiv_id, base_name, out_dir):
    if not arxiv_id:
        print("无法解析 arXiv ID，跳过 TeX 下载。")
        return None

    out_path = os.path.join(out_dir, f"{base_name}_source.tar.gz")
    if os.path.exists(out_path):
        print(f"[*] 已存在 arXiv 源文件，跳过: {os.path.basename(out_path)}")
        return out_path

    url = f"https://arxiv.org/e-print/{arxiv_id}"
    try:
        print(f"[+] 正在下载 arXiv TeX: {arxiv_id}")
        res = HTTP_SESSION.get(url, stream=True, timeout=60)
        res.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"  [+] TeX 下载成功: {out_path}")
        return out_path
    except Exception as e:
        print(e)
        return None

def select_and_download_llm_tex(client, model):
    hf_dir = os.path.join(TARGET_DIR, "HuggingFace")
    if not os.path.exists(hf_dir):
        print("今日 HuggingFace 目录不存在，跳过 LLM 论文筛选。")
        return

    selection_path = os.path.join(hf_dir, "llm_paper_selection.json")
    if os.path.exists(selection_path):
        print("[*] 已存在 LLM 论文选择记录，跳过重复筛选。")
        return

    candidates = collect_hf_candidates()
    if not candidates:
        print("没有找到可用的论文摘要，无法筛选 LLM 论文。")
        return

    selected, reason = choose_best_llm_paper(client, model, candidates)
    if not selected:
        print("无法确定最佳 LLM 论文，跳过 TeX 下载。")
        return

    base_name = os.path.basename(selected["summary_path"]).replace("_summary.md", "")
    tex_path = download_arxiv_source(selected["arxiv_id"], base_name, hf_dir)

    record = {
        "date": TODAY,
        "selected_id": selected["id"],
        "title": selected["title"],
        "arxiv_id": selected["arxiv_id"],
        "summary_path": selected["summary_path"],
        "tex_path": tex_path,
        "reason": reason
    }
    try:
        with open(selection_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        print(f"[+] LLM 论文选择记录已保存: {selection_path}")
    except Exception as e:
        print(e)

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

    print("\n--- 开始筛选 LLM 潜力论文并下载 TeX ---")
    select_and_download_llm_tex(client, model)
        
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
        if translation:
            with open(zh_readme_path, "w", encoding="utf-8") as f:
                f.write(translation)
            print(f"  [+] 翻译保存成功: {zh_readme_path}")
            
        time.sleep(2)

if __name__ == "__main__":
    process_files()