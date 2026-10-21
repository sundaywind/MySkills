# C:\Users\Wind\.gemini\config\skills\ai-morning-paper-publisher\scripts\fetch_news.py
import os
import re
import sys
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

# 默认 RSS 源列表 (包含 AI 学术、科技前沿、开源动态等)
DEFAULT_RSS_FEEDS = {
    "ArXiv AI": "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortby=submittedDate&sortorder=descending&max_results=10",
    "Solidot (科技动态)": "https://www.solidot.org/index.rss",
    "Hugging Face (每日学术)": "https://huggingface.co/feeed/arxiv"
}

def get_deepseek_key():
    """从环境变量或 Obsidian 知识库中安全获取 DeepSeek API Key"""
    # 1. 优先尝试环境变量
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if api_key:
        return api_key

    # 2. 尝试从本地 Obsidian 大脑获取
    obsidian_key_path = Path(r"D:\Wind\大脑\Study\AI\AI开放平台API-keys.md")
    if obsidian_key_path.exists():
        try:
            with open(obsidian_key_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 找到 DeepSeek 这一节的内容，防止错匹到其他平台 (如小米 MiMo) 的 Key
            ds_section = re.search(r"DeepSeek.*?(?=###|\Z)", content, re.DOTALL | re.IGNORECASE)
            if ds_section:
                ds_content = ds_section.group(0)
                match = re.search(r"sk-[a-zA-Z0-9]+", ds_content)
                if match:
                    return match.group(0)
        except Exception as e:
            print(f"[DEBUG] 读取 Obsidian API Key 失败: {e}")
            
    return None

def fetch_rss_items(feed_url):
    """抓取 RSS 并解析，支持 Atom 与 RSS 2.0 格式"""
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(feed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        
        # 兼容 Atom 格式 (如 arXiv)
        namespaces = {'ns': 'http://www.w3.org/2005/Atom'}
        atom_entries = root.findall('.//ns:entry', namespaces)
        if atom_entries:
            for entry in atom_entries:
                title_node = entry.find('ns:title', namespaces)
                summary_node = entry.find('ns:summary', namespaces)
                link_node = entry.find('ns:link', namespaces)
                
                title = title_node.text.strip() if title_node is not None else ""
                summary = summary_node.text.strip() if summary_node is not None else ""
                link = link_node.attrib.get('href', '') if link_node is not None else ""
                
                # 简单清理多余的换行
                title = re.sub(r'\s+', ' ', title)
                summary = re.sub(r'\s+', ' ', summary)
                
                items.append({"title": title, "summary": summary[:300], "link": link})
            return items

        # 兼容标准 RSS 2.0 格式 (如 Solidot)
        channel_items = root.findall('.//item')
        for item in channel_items:
            title_node = item.find('title')
            desc_node = item.find('description')
            link_node = item.find('link')
            
            title = title_node.text.strip() if title_node is not None else ""
            summary = desc_node.text.strip() if desc_node is not None else ""
            link = link_node.text.strip() if link_node is not None else ""
            
            # 清洗 HTML 标签
            summary = re.sub(r'<[^>]+>', '', summary)
            summary = re.sub(r'\s+', ' ', summary)
            
            items.append({"title": title, "summary": summary[:300], "link": link})
            
    except Exception as e:
        print(f"[WARN] 抓取源 {feed_url} 失败: {e}")
    return items

def evaluate_news_with_llm(api_key, title, summary):
    """调用 DeepSeek 平台对新闻进行打分过滤 (0-100)"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""你是一个 AI 行业前沿资讯的筛选助手。请根据下面新闻的标题和摘要，对它的“行业价值与重要性”进行打分（0-100分）。

打分标准：
- 90-100分：重大技术突破（如 GPT-5、Claude 3.5 新版、开源领域标杆级模型如 Llama/DeepSeek 最新主力模型发布）。
- 80-89分：知名大厂产品更新（如主流 IDE 支持新插件、常规模型更新、重要行业监管政策、核心人事变动）。
- 50-79分：一般的应用更新、无突破性的学术论文、非核心厂商的融资。
- 50分以下：与 AI 行业无关、或者完全没有行业影响力的资讯。

新闻标题：{title}
新闻摘要：{summary}

请根据你的判断直接给出一个 0-100 之间的整数分数。
【重要要求】：请有且仅返回一个整数数字，不要有任何其他文字说明！"""

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 10
    }
    
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            content = result["choices"][0]["message"]["content"].strip()
            # 提取整数
            score_match = re.search(r'\d+', content)
            if score_match:
                return int(score_match.group(0))
        else:
            print(f"[DEBUG] API 报错，状态码: {resp.status_code}, 响应: {resp.text}")
    except Exception as e:
        print(f"[DEBUG] 请求 DeepSeek 发生异常: {e}")
    return 50 # 默认降级分数

def main():
    print("=== 开始搜集今日 AI 行业资讯 ===")
    api_key = get_deepseek_key()
    if not api_key:
        print("[ERROR] 未获取到 DeepSeek API Key，请配置环境变量 DEEPSEEK_API_KEY")
        sys.exit(1)
    
    all_news = []
    for source_name, feed_url in DEFAULT_RSS_FEEDS.items():
        print(f"正在抓取源: {source_name}...")
        items = fetch_rss_items(feed_url)
        print(f"成功获取 {len(items)} 条资讯。")
        for item in items:
            item["source"] = source_name
            all_news.append(item)
            
    print(f"\n=== 开始使用大模型筛选高价值资讯 (过滤分数 >= 80) ===")
    selected_news = []
    
    # 限制分析前 15 条，防止调用 API 过度消耗 token
    for idx, item in enumerate(all_news[:15], 1):
        print(f"[{idx}/15] 正在评估: {item['title'][:30]}...")
        score = evaluate_news_with_llm(api_key, item["title"], item["summary"])
        print(f"    -> 评分: {score}")
        if score >= 80:
            item["score"] = score
            selected_news.append(item)
            
    print(f"\n=== 筛选结果 (共 {len(selected_news)} 条高价值资讯) ===")
    if not selected_news:
        print("今天暂无 80 分以上的重大 AI 行业要闻。")
    else:
        for idx, item in enumerate(selected_news, 1):
            print(f"\n#{idx} 【{item['source']}】{item['title']} (评分: {item['score']})")
            print(f"摘要: {item['summary'][:150]}...")
            print(f"链接: {item['link']}")

if __name__ == "__main__":
    main()
