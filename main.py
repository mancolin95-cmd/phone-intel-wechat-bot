import os
import requests
import hashlib
import feedparser
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import sys

# =========================
# 环境变量检查
# =========================
WECHAT_WEBHOOK = os.environ.get("WECHAT_WEBHOOK")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not WECHAT_WEBHOOK or not DEEPSEEK_API_KEY:
    print("错误：WECHAT_WEBHOOK 或 DEEPSEEK_API_KEY 未设置，请检查 GitHub Secrets")
    sys.exit(1)

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
# RSSHub 社交媒体
# =========================
RSSHUB = "https://rsshub.rssforever.com"
SOCIAL_PLATFORMS = ["weibo", "bilibili", "xiaohongshu", "douyin"]

# =========================
# 去重缓存
# =========================
processed_hashes = set()
daily_news = []

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
# 处理 Google RSS 原始链接（社交媒体也用此方法） 
# =========================
def get_original_link(entry):
    link = getattr(entry, "link", "")
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
    if not title or not link or not is_today(published_struct):
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
# DeepSeek 大事件总结
# =========================
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

def summarize_daily_event(news_list):
    if not news_list:
        return None
    content = "\n".join([f"{n['time']} | {n['brand']} | {n['title']} | {n['link']}" for n in news_list])
    prompt = f"""
你是手机行业情报分析助手。

任务：
1. 将以下今日新闻按事件关联性聚合，每个事件编号（事件1、事件2、事件3…）。
2. 对每个事件生成时间线（时间节点按新闻发布时间排序）。
3. 每个时间节点包含：
   - 时间（YYYY-MM-DD HH:MM）
   - 核心内容（一句话总结新闻）
   - 原新闻链接
4. 每个事件写一个150字以内概述，总结事件整体内容和影响。
5. 只返回结构化 Markdown 文本，示例：
事件1：
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
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("DeepSeek 日总结错误:", e)
        return None

# =========================
# 企业微信推送
# =========================
def send_daily_event(event_summary):
    if not event_summary:
        print("没有事件总结可推送")
        return
    # 限制 1800 字
    message = f"## 📱 今日手机行业大事件\n\n{event_summary[:1800]}"
    data = {"msgtype": "markdown", "markdown": {"content": message}}
    try:
        response = requests.post(WECHAT_WEBHOOK, json=data, timeout=10)
        print("企业微信响应状态:", response.status_code)
        print("响应内容:", response.text)
        if response.status_code != 200:
            print("企业微信发送失败")
    except Exception as e:
        print("企业微信推送错误:", e)

# =========================
# 科技媒体抓取
# =========================
def fetch_media_news():
    for rss in MEDIA_RSS:
        try:
            feed = feedparser.parse(rss)
        except Exception as e:
            print(f"解析媒体 RSS 失败: {rss}", e)
            continue
        for entry in feed.entries[:10]:
            title = getattr(entry, "title", None)
            link = getattr(entry, "link", None)
            published_struct = entry.get("published_parsed")
            for brand, keywords in BRANDS.items():
                if title and any(k.lower() in title.lower() for k in keywords):
                    collect_news(brand, title, link, published_struct)
                    break

# =========================
# 社交媒体抓取
# =========================
def generate_social_rss():
    rss_list = []
    for brand, keywords in BRANDS.items():
        keyword = keywords[0]
        for platform in SOCIAL_PLATFORMS:
            rss_list.append((brand, f"{RSSHUB}/{platform}/search/{keyword}"))
    return rss_list

def fetch_social_news():
    for brand, rss in generate_social_rss():
        try:
            feed = feedparser.parse(rss)
        except Exception as e:
            print(f"解析社交 RSS 失败: {rss}", e)
            continue
        for entry in feed.entries[:10]:
            title = getattr(entry, "title", None)
            link = getattr(entry, "link", None)
            published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            collect_news(brand, title, link, published_struct)

# =========================
# 主程序
# =========================
def main():
    try:
        print("开始抓取手机行业情报...")
        global daily_news
        daily_news = []

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
    except Exception as e:
        print("主程序运行出错:", e)

if __name__ == "__main__":
    main()
