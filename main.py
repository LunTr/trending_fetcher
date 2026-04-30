import os
import datetime
import urllib.request
import requests
from bs4 import BeautifulSoup
import string
import re
import urllib3

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
DOWNLOADED_ARXIV_IDS = set()

# GitHub 历史记录文件
GITHUB_HISTORY_FILE = "downloaded_github_history.txt"
DOWNLOADED_GITHUB_REPOS = set()

if os.path.exists(GITHUB_HISTORY_FILE):
    with open(GITHUB_HISTORY_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                DOWNLOADED_GITHUB_REPOS.add(line.strip())

def create_dir(dir_name):
    # 更改目录结构：按 日期/来源 归类
    path = os.path.join(os.getcwd(), TODAY, dir_name)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def sanitize_filename(filename):
    valid_chars = f"-_.() {string.ascii_letters}{string.digits}"
    return ''.join(c for c in filename if c in valid_chars)[:150]

def download_github_trending():
    print("开始抓取 GitHub Trending 前5项目...")
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
                    print(f"[-] 仓库已存在，跳过: {repo_id}")
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
                print(f"[+] 获取成功: {repo_id}")
                
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
                            print(f"  [+] README 下载成功: {repo_id} (分支:{branch})")
                            readme_downloaded = True
                            
                            # 保存到历史记录中
                            DOWNLOADED_GITHUB_REPOS.add(repo_id)
                            with open(GITHUB_HISTORY_FILE, 'a', encoding='utf-8') as hf:
                                hf.write(f"{repo_id}\n")
                                
                            break
                    except Exception:
                        pass
                
                if not readme_downloaded:
                    print(f"  [-] 未能下载 README 或不存在: {repo_id}")
                    # 即使没有Readme也记录到历史，以免之后反复下载空项目
                    DOWNLOADED_GITHUB_REPOS.add(repo_id)
                    with open(GITHUB_HISTORY_FILE, 'a', encoding='utf-8') as hf:
                        hf.write(f"{repo_id}\n")
                
            if new_repos_count == 0:
                print("没有新的 GitHub Trending 项目需要抓取。")
                f.write("今日无新项目更新。\n")
                
        print("GitHub 概括和 README 保存完成！\n")
    except Exception as e:
        print(f"抓取 GitHub 时出错: {e}\n")

def download_arxiv_pdf(arxiv_id, title, dir_path):
    if arxiv_id in DOWNLOADED_ARXIV_IDS:
        print(f"  [-] 论文已存在，跳过: {arxiv_id}")
        return False
        
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    safe_title = sanitize_filename(title)
    file_path = os.path.join(dir_path, f"{safe_title}_{arxiv_id}.pdf")
    
    try:
        print(f"  [+] 正在下载 PDF: {arxiv_id} ...")
        res = session.get(pdf_url, stream=True, timeout=30)
        res.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        DOWNLOADED_ARXIV_IDS.add(arxiv_id)
        return True
    except Exception as e:
        print(f"  [!] 下载失败 {arxiv_id}: {e}")
        return False

def download_huggingface_daily_papers():
    print("开始获取 HuggingFace Daily Papers...")
    dir_path = create_dir("HuggingFace")
    
    url = f"https://huggingface.co/api/daily_papers?date={TODAY}"
    try:
        response = session.get(url, timeout=15)
        if response.status_code in [404, 400]:
            print(f"  [!] 今天 ({TODAY}) 的数据可能尚未生成或不存在，获取最新一期的摘要...")
            url = "https://huggingface.co/api/daily_papers"
            response = session.get(url, timeout=15)
            
        response.raise_for_status()
        papers = response.json()
        
        print(f"找到 {len(papers)} 篇 Daily Papers。")
        for p in papers:
            paper_info = p.get('paper', {})
            title = paper_info.get('title', 'Unknown')
            arxiv_id = paper_info.get('id', '')
            
            if arxiv_id:
                download_arxiv_pdf(arxiv_id, title, dir_path)
        print("HuggingFace Daily Papers 抓取完成！\n")
    except Exception as e:
        print(f"抓取 HuggingFace Daily Papers 时出错: {e}\n")

if __name__ == "__main__":
    print(f"正在使用的系统代理配置: {system_proxies}\n")
    
    download_github_trending()
    download_huggingface_daily_papers()
    
    print("所有抓取与下载任务执行完毕！")