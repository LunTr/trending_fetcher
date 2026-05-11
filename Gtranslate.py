import requests, time

def translate_google(text: str, target="zh-CN", source="auto") -> str:
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    # 返回结构是嵌套列表，把所有片段拼起来
    return "".join(seg[0] for seg in r.json()[0] if seg[0])

def translate_large(text: str, chunk_size=4000) -> str:
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    results = []
    for chunk in chunks:
        results.append(translate_google(chunk))
        time.sleep(0.3)  # 避免触发频率限制
    return "".join(results)