import os
import requests
import hashlib
import feedparser
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# =========================
# 监控品牌
# =========================
BRANDS = {
    "华为": ["华为", "Mate", "Pura", "麒麟"],
    "小米": ["小米", "Redmi"],
    "OPPO": ["OPPO", "Find"],
    "vivo": ["vivo", "iQOO"],
    "荣耀": ["荣耀", "Magic"],
    "Apple": ["Apple", "iPhone"],
    "三星": ["三星", "Galaxy"]
}

# =========================
# 科技媒体 RSS
# =========================
MEDIA_RSS = [
    "https://www.ithome.com/rss/",
    "https://36kr.com/feed",
    "https://www.huxiu.com/rss/0.xml",
    "https://www.tmtpost.com/rss",
    "https://www.ifanr.com/feed",
    "https://www.leikeji.com/rss",
    "https://www.mydrivers.com/rss.xml",
]

# =========================
# RSSHub（社交媒体）
# =========================
RSSHUB = "https://rsshub.rssforever.com"
SOCIAL_PLATFORMS = ["weibo", "bilibili", "xiaohongshu", "douyin"]

# =========================
# API配置
# =========================
WECHAT_WEBHOOK = os.environ["WECHAT_WEBHOOK"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# =========================
# 去重缓存
# =========================
processed_hashes = set()
daily_news = []

# =========================
# 企业微信推送
# =========================
def send_daily_event(event_summary):
    message = f"## 📱 今日手机行业大事件\n\n{event_summary}"
    data = {
        "msgtype": "markdown",
        "markdown": {"content": message}
    }
    response = requests.post(WECHAT_WEBHOOK, json=data)
    if response.status_code != 200:
        print("企业微信发送失败:", response.text)

# =========================
# 时间过滤
# =========================
def is_today(published_struct):
    if not published_struct:
        return False
    news_date = datetime(*published_struct[:6])
    today = datetime.now()
    return news_date.date() == today.date()

# =========================
# 处理 Google RSS 原始链接
# =========================
def get_original_link(entry):
    link = entry.get("link", "")
    if "news.google.com" in link and entry.get("id"):
        link_candidate = entry["id"]
        if link_candidate.startswith("http"):
            link = link_candidate
        else:
            parsed = urlparse(link_candidate)
            qs = parse_qs(parsed.query)
            if "url" in qs:
                link = qs["url"][0]
    return link

# =========================
# 收集新闻
# =========================
def collect_news(brand, title, link, published_struct):
    if not is_today(published_struct):
        return
    h = hashlib.md5(title.encode()).hexdigest()
    if h in processed_hashes:
        return
    processed_hashes.add(h)
    news_time = datetime(*published_struct[:6]).strftime("%Y-%m-%d %H:%M")
    daily_news.append({
        "brand": brand,
        "title": title,
        "link": link,
        "time": news_time
    })

# =========================
# DeepSeek大事件总结
# =========================
def summarize_daily_event(news_list):
    if not news_list:
        return None

    content = "\n".join([f"{n['time']} | {n['brand']} | {n['title']} | {n['link']}" for n in news_list])

    prompt = f"""
你是手机行业情报分析助手。

任务：
1. 将以下今日新闻按事件关联性进行聚合，每个事件编号（事件1、事件2、事件3…）。
2. 对每个事件生成时间线（时间节点按新闻发布时间排序）。
3. 每个时间节点包含：
   - 时间（YYYY-MM-DD HH:MM）
   - 核心内容（一句话总结新闻）
   - 原新闻链接
4. 每个事件还需写一个150字以内的事件概述，总结事件的整体内容和影响。
5. 只返回结构化文本，Markdown风格，示例如下：

事件1：
概述：事件概述内容
时间线：
- YYYY-MM-DD HH:MM：核心内容内容 [🔗原文](新闻链接)
- YYYY-MM-DD HH:MM：核心内容内容 [🔗原文](新闻链接)

事件2：
概述：事件概述内容
时间线：
- YYYY-MM-DD HH:MM：核心内容内容 [🔗原文](新闻链接)

新闻列表：
{content}
"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800
    }

    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("DeepSeek日总结错误:", e)
        return None

# =========================
# 新闻抓取
# =========================
def fetch_google_news():
    for brand, keywords in BRANDS.items():
        keyword = " OR ".join(keywords)
        url = f"https://news.google.com/rss/search?q={keyword}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            published_struct = entry.get("published_parsed")
            link = get_original_link(entry)
            collect_news(brand, entry.title, link, published_struct)

def fetch_media_news():
    for rss in MEDIA_RSS:
        feed = feedparser.parse(rss)
        for entry in feed.entries[:10]:
            title = entry.title
            link = entry.link
            published_struct = entry.get("published_parsed")
            for brand, keywords in BRANDS.items():
                for k in keywords:
                    if k.lower() in title.lower():
                        collect_news(brand, title, link, published_struct)
                        break

def generate_social_rss():
    rss_list = []
    for brand, keywords in BRANDS.items():
        keyword = keywords[0]
        for platform in SOCIAL_PLATFORMS:
            url = f"{RSSHUB}/{platform}/search/{keyword}"
            rss_list.append((brand, url))
    return rss_list

def fetch_social_news():
    rss_list = generate_social_rss()
    for brand, rss in rss_list:
        feed = feedparser.parse(rss)
        for entry in feed.entries[:10]:
            title = entry.title
            link = entry.link
            published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            collect_news(brand, title, link, published_struct)

# =========================
# 主程序
# =========================
def main():
    print("开始抓取手机行业情报...")

    global daily_news
    daily_news = []

    fetch_google_news()
    fetch_media_news()
    fetch_social_news()

    print(f"今日收集新闻条数: {len(daily_news)}")

    summary = summarize_daily_event(daily_news)
    if summary:
        send_daily_event(summary)
        print("已推送今日大事件总结")
    else:
        print("今日大事件总结生成失败")

    print("抓取完成")

if __name__ == "__main__":
    main()
