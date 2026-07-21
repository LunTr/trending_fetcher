import sys

sys.dont_write_bytecode = True

import os
import datetime
import urllib.request
import requests
from bs4 import BeautifulSoup
import string
import re
import urllib3
import json
import fitz

# 禁用安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 获取系统代理
system_proxies = urllib.request.getproxies()

# 配置会话
session = requests.Session()
if system_proxies:
    session.proxies.update(system_proxies)

# 忽略SSL证书验证，解决系统代理或证书缺失引起的 SSL 错误
session.verify = False

# 确保请求不过期且信任系统代理
session.trust_env = True
# 伪装User-Agent，否则很容易被拦截
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
})

TODAY = datetime.datetime.now().strftime('%Y-%m-%d')
DATA_ROOT = os.path.abspath(
    os.environ.get("TRENDING_FETCHER_DATA_DIR")
    or os.path.join(os.path.dirname(__file__), "..")
)
DOWNLOADED_ARXIV_IDS = set()
ARXIV_HISTORY_FILE = os.path.join(DATA_ROOT, "downloaded_arxiv_history.json")
HF_DAILY_LIMIT = 20

# GitHub 历史记录文件
GITHUB_HISTORY_FILE = os.path.join(DATA_ROOT, "downloaded_github_history.txt")
DOWNLOADED_GITHUB_REPOS = set()

def emit(reporter, event, **payload):
    if reporter:
        reporter({"event": event, **payload})

def log(reporter, message, **payload):
    print(message)
    emit(reporter, "log", message=message, **payload)

def load_github_history():
    repos = set()
    if os.path.exists(GITHUB_HISTORY_FILE):
        with open(GITHUB_HISTORY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    repos.add(line.strip())
    return repos

DOWNLOADED_GITHUB_REPOS.update(load_github_history())

def create_dir(dir_name):
    # 更改目录结构：按 日期/来源 归类
    path = os.path.join(DATA_ROOT, TODAY, dir_name)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def sanitize_filename(filename):
    valid_chars = f"-_.() {string.ascii_letters}{string.digits}"
    return ''.join(c for c in filename if c in valid_chars)[:150]

def extract_arxiv_id_from_name(name):
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", name)
    if not match:
        return None
    return f"{match.group(1)}{match.group(2) or ''}"

def load_arxiv_history():
    if not os.path.exists(ARXIV_HISTORY_FILE):
        return {}
    try:
        with open(ARXIV_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_arxiv_history(history):
    with open(ARXIV_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2, sort_keys=True)

def record_arxiv_id(arxiv_id, date_str=None):
    if not arxiv_id:
        return
    date_str = date_str or TODAY
    existing_date = ARXIV_HISTORY.get(arxiv_id)
    if not existing_date or date_str > existing_date:
        ARXIV_HISTORY[arxiv_id] = date_str
        save_arxiv_history(ARXIV_HISTORY)
    DOWNLOADED_ARXIV_IDS.add(arxiv_id)

ARXIV_HISTORY = load_arxiv_history()
DOWNLOADED_ARXIV_IDS.update(ARXIV_HISTORY.keys())

def today_arxiv_download_count():
    return sum(1 for date_str in ARXIV_HISTORY.values() if date_str == TODAY)

def configure_runtime(data_root=None, date_str=None):
    global TODAY, DATA_ROOT, ARXIV_HISTORY_FILE, GITHUB_HISTORY_FILE, ARXIV_HISTORY

    if data_root:
        DATA_ROOT = os.path.abspath(data_root)
    os.makedirs(DATA_ROOT, exist_ok=True)

    if date_str:
        TODAY = date_str

    ARXIV_HISTORY_FILE = os.path.join(DATA_ROOT, "downloaded_arxiv_history.json")
    GITHUB_HISTORY_FILE = os.path.join(DATA_ROOT, "downloaded_github_history.txt")

    DOWNLOADED_GITHUB_REPOS.clear()
    DOWNLOADED_GITHUB_REPOS.update(load_github_history())

    ARXIV_HISTORY = load_arxiv_history()
    DOWNLOADED_ARXIV_IDS.clear()
    DOWNLOADED_ARXIV_IDS.update(ARXIV_HISTORY.keys())

def download_github_trending(reporter=None):
    log(reporter, "开始抓取 GitHub Trending 前5项目...", stage="github")
    dir_path = create_dir("GitHub")
    url = "https://github.com/trending"
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        repos = soup.find_all('article', class_='Box-row')[:5]
        
        summary_path = os.path.join(dir_path, "github_trending_summary.txt")
        new_repos_count = 0
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"GitHub Trending Top ({TODAY})\n")
            f.write("="*40 + "\n\n")
            
            for repo in repos:
                # 提取仓库 ID (ex: author/repo_name)
                h2 = repo.find('h2', class_='h3 lh-condensed')
                repo_id = h2.text.strip().replace('\n', '').replace(' ', '').strip('/')
                
                if repo_id in DOWNLOADED_GITHUB_REPOS:
                    log(reporter, f"[-] 仓库已存在，跳过: {repo_id}", stage="github", repo=repo_id)
                    continue
                    
                new_repos_count += 1
                
                # 更改文件夹命名为 用户_项目 的格式
                repo_name = sanitize_filename(repo_id.replace('/', '_'))
                
                p_desc = repo.find('p', class_='col-9 color-fg-muted my-1 pr-4')
                if p_desc is None:
                    p_desc_alt = repo.find('p', class_='col-9 color-fg-muted my-1 pr-4') # Sometimes class changes, usually it's just 'p' containing description
                    if p_desc_alt is None:
                        # Fallback for description
                        p_desc = repo.find('p')
                        
                desc = p_desc.text.strip() if p_desc else "No description provided."
                
                text = f"{new_repos_count}. {repo_id}\n   功能概括：{desc}\n\n"
                f.write(text)
                log(reporter, f"[+] 获取成功: {repo_id}", stage="github", repo=repo_id)
                
                # 为每个项目创建专门的文件夹
                repo_dir = os.path.join(dir_path, repo_name)
                if not os.path.exists(repo_dir):
                    os.makedirs(repo_dir)
                    
                # 尝试从 raw.githubusercontent.com 下载 README (常用分支: main / master)
                branches = ['main', 'master']
                readme_downloaded = False
                for branch in branches:
                    readme_url = f"https://raw.githubusercontent.com/{repo_id}/{branch}/README.md"
                    try:
                        rm_resp = session.get(readme_url, timeout=15)
                        if rm_resp.status_code == 200:
                            readme_path = os.path.join(repo_dir, "README.md")
                            with open(readme_path, "w", encoding="utf-8") as rmf:
                                rmf.write(rm_resp.text)
                            log(reporter, f"  [+] README 下载成功: {repo_id} (分支:{branch})", stage="github", repo=repo_id)
                            readme_downloaded = True
                            
                            # 保存到历史记录中
                            DOWNLOADED_GITHUB_REPOS.add(repo_id)
                            with open(GITHUB_HISTORY_FILE, 'a', encoding='utf-8') as hf:
                                hf.write(f"{repo_id}\n")
                                
                            break
                    except Exception:
                        pass
                
                if not readme_downloaded:
                    log(reporter, f"  [-] 未能下载 README 或不存在: {repo_id}", stage="github", repo=repo_id)
                    # 即使没有Readme也记录到历史，以免之后反复下载空项目
                    DOWNLOADED_GITHUB_REPOS.add(repo_id)
                    with open(GITHUB_HISTORY_FILE, 'a', encoding='utf-8') as hf:
                        hf.write(f"{repo_id}\n")
                
            if new_repos_count == 0:
                log(reporter, "没有新的 GitHub Trending 项目需要抓取。", stage="github")
                f.write("今日无新项目更新。\n")
                
        emit(reporter, "stats", github_new=new_repos_count)
        log(reporter, "GitHub 概括和 README 保存完成！\n", stage="github")
    except Exception as e:
        log(reporter, f"抓取 GitHub 时出错: {e}\n", stage="github", level="error")

def download_arxiv_pdf(arxiv_id, title, dir_path, reporter=None):
    if arxiv_id in DOWNLOADED_ARXIV_IDS:
        log(reporter, f"  [-] 论文已存在，跳过: {arxiv_id}", stage="hf-pdf", arxiv_id=arxiv_id)
        return False
        
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    safe_title = sanitize_filename(title)
    file_path = os.path.join(dir_path, f"{safe_title}_{arxiv_id}.pdf")

    if os.path.exists(file_path):
        log(reporter, f"  [-] PDF 已存在，跳过: {arxiv_id}", stage="hf-pdf", arxiv_id=arxiv_id)
        record_arxiv_id(arxiv_id)
        return False
    
    temp_path = f"{file_path}.part"
    for attempt in range(1, 3):
        try:
            log(
                reporter,
                f"  [+] 正在下载 PDF: {arxiv_id} ...",
                stage="hf-pdf",
                arxiv_id=arxiv_id,
                title=title,
                file_path=file_path,
            )
            res = session.get(pdf_url, stream=True, timeout=30)
            res.raise_for_status()
            total = int(res.headers.get("content-length") or 0)
            downloaded = 0
            last_emit = 0
            emit(
                reporter,
                "download_start",
                stage="hf-pdf",
                arxiv_id=arxiv_id,
                title=title,
                file_name=os.path.basename(file_path),
                file_path=file_path,
                downloaded_bytes=0,
                total_bytes=total,
                percent=0 if total else None,
            )
            with open(temp_path, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded - last_emit >= 262144 or (total and downloaded >= total):
                        last_emit = downloaded
                        emit(
                            reporter,
                            "download_progress",
                            stage="hf-pdf",
                            arxiv_id=arxiv_id,
                            title=title,
                            file_name=os.path.basename(file_path),
                            file_path=file_path,
                            downloaded_bytes=downloaded,
                            total_bytes=total,
                            percent=round(downloaded * 100 / total, 1) if total else None,
                        )
        except Exception as e:
            remove_file_if_exists(temp_path)
            log(reporter, f"  [!] 下载失败 {arxiv_id}: {e}", stage="hf-pdf", arxiv_id=arxiv_id, level="error")
            return False

        try:
            validate_downloaded_pdf(temp_path)
        except Exception as e:
            remove_file_if_exists(temp_path)
            if attempt < 2:
                log(
                    reporter,
                    f"  [!] PDF 解析失败，正在重新抓取 {arxiv_id}: {e}",
                    stage="hf-pdf",
                    arxiv_id=arxiv_id,
                    level="warning",
                )
                continue
            log(
                reporter,
                f"  [!] PDF 重新抓取后仍无法解析 {arxiv_id}: {e}",
                stage="hf-pdf",
                arxiv_id=arxiv_id,
                level="error",
            )
            return False

        try:
            os.replace(temp_path, file_path)
            record_arxiv_id(arxiv_id)
        except Exception as e:
            remove_file_if_exists(temp_path)
            log(reporter, f"  [!] 保存 PDF 失败 {arxiv_id}: {e}", stage="hf-pdf", arxiv_id=arxiv_id, level="error")
            return False
        emit(
            reporter,
            "download_done",
            stage="hf-pdf",
            arxiv_id=arxiv_id,
            title=title,
            file_name=os.path.basename(file_path),
            file_path=file_path,
            downloaded_bytes=downloaded,
            total_bytes=total,
            percent=100 if total else None,
        )
        return True

    return False


def validate_downloaded_pdf(file_path):
    with fitz.open(file_path) as document:
        if document.page_count <= 0:
            raise ValueError("PDF contains no pages")
        for page_number in range(document.page_count):
            document.load_page(page_number).get_text("text")


def remove_file_if_exists(file_path):
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass

def download_huggingface_daily_papers(reporter=None):
    log(reporter, "开始获取 HuggingFace Daily Papers...", stage="hf-list")
    dir_path = create_dir("HuggingFace")
    today_count = today_arxiv_download_count()
    remaining_quota = max(0, HF_DAILY_LIMIT - today_count)
    emit(reporter, "stats", hf_today_downloaded=today_count, hf_daily_limit=HF_DAILY_LIMIT)
    log(
        reporter,
        f"今日已下载 arXiv PDF {today_count}/{HF_DAILY_LIMIT}，剩余额度 {remaining_quota}。",
        stage="hf-list",
    )
    if remaining_quota <= 0:
        emit(reporter, "queue", stage="hf-pdf", current=0, total=0)
        emit(reporter, "stats", hf_downloaded=0, hf_skipped_or_failed=0)
        log(reporter, "今日下载数量已达上限，跳过 HuggingFace Daily Papers PDF 下载。", stage="hf-pdf")
        return
    
    url = f"https://huggingface.co/api/daily_papers?date={TODAY}"
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
        papers = response.json()
        if not isinstance(papers, list):
            print("Daily Papers 返回格式异常，无法解析。")
            return

        def get_rise_score(item):
            for key in ("upvotes", "upvoteCount", "upvote_count", "votes", "score", "trend", "trend_score", "rise"):
                value = item.get(key)
                if isinstance(value, (int, float)):
                    return value
            paper = item.get('paper', {})
            for key in ("upvotes", "upvoteCount", "upvote_count", "votes", "score", "trend", "trend_score", "rise"):
                value = paper.get(key)
                if isinstance(value, (int, float)):
                    return value
            return 0

        papers_sorted = sorted(papers, key=get_rise_score, reverse=True)
        def is_new_paper(item):
            paper = item.get('paper', {})
            arxiv_id = paper.get('id', '')
            return bool(arxiv_id) and arxiv_id not in DOWNLOADED_ARXIV_IDS

        unique_papers = [p for p in papers_sorted if is_new_paper(p)]
        selected = unique_papers[:remaining_quota]
        log(
            reporter,
            f"去重后 {len(unique_papers)} 篇Daily Papers，按剩余额度取前 {len(selected)} 篇。",
            stage="hf-list",
            total=len(selected),
        )
        emit(reporter, "queue", stage="hf-pdf", current=0, total=len(selected))

        downloaded_count = 0
        skipped_or_failed = 0
        for idx, p in enumerate(selected, 1):
            paper_info = p.get('paper', {})
            title = paper_info.get('title', 'Unknown')
            arxiv_id = paper_info.get('id', '')
            
            if arxiv_id:
                emit(reporter, "queue", stage="hf-pdf", current=idx, total=len(selected), arxiv_id=arxiv_id, title=title)
                if download_arxiv_pdf(arxiv_id, title, dir_path, reporter=reporter):
                    downloaded_count += 1
                else:
                    skipped_or_failed += 1
        emit(
            reporter,
            "stats",
            hf_downloaded=downloaded_count,
            hf_skipped_or_failed=skipped_or_failed,
            hf_today_downloaded=today_count + downloaded_count,
            hf_daily_limit=HF_DAILY_LIMIT,
        )
        log(reporter, "HuggingFace Daily Papers 抓取完成！\n", stage="hf-pdf")
    except Exception as e:
        log(reporter, f"抓取 HuggingFace Daily Papers 时出错: {e}\n", stage="hf-list", level="error")

def update_arxiv_history_file(reporter=None):
    import update_arxiv_history
    history = update_arxiv_history.build_history(DATA_ROOT)
    with open(ARXIV_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, sort_keys=True)
    log(reporter, f"Updated {ARXIV_HISTORY_FILE} with {len(history)} entries.", stage="history")

def build_today_kb(reporter=None):
    try:
        import createbase
        source_dir = os.path.join(DATA_ROOT, TODAY)
        kb_dir = os.path.join(DATA_ROOT, "kb_store")
        api_key_path = os.path.join(DATA_ROOT, "API_KEY.json")
        log(reporter, "Starting offline KB build...", stage="kb-build", source_dir=source_dir)
        createbase.build_kb(source_dir=source_dir, kb_dir=kb_dir, api_key_path=api_key_path, reporter=reporter)
    except Exception as e:
        log(reporter, f"[!] KB build skipped: {e}", stage="kb-build", level="error")

def run_main(data_root=None, reporter=None, build_index=True):
    configure_runtime(data_root=data_root)
    log(reporter, f"正在使用的系统代理配置: {system_proxies}\n", stage="proxy")

    log(reporter, "更新 arXiv 下载历史记录...", stage="history")
    update_arxiv_history_file(reporter=reporter)

    # 重新加载更新后的历史记录
    global ARXIV_HISTORY
    ARXIV_HISTORY = load_arxiv_history()
    DOWNLOADED_ARXIV_IDS.update(ARXIV_HISTORY.keys())

    download_github_trending(reporter=reporter)
    download_huggingface_daily_papers(reporter=reporter)

    log(reporter, "所有抓取与下载任务执行完毕！", stage="main")
    if build_index:
        build_today_kb(reporter=reporter)

if __name__ == "__main__":
    run_main()
