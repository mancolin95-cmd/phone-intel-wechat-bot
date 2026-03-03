import os
import requests
import hashlib
import feedparser
from datetime import datetime

# 监控品牌
BRANDS = ["华为", "小米", "OPPO", "vivo", "荣耀", "一加", "三星", "Apple"]

# 科技媒体 RSS
MEDIA_RSS = [
    "https://www.ithome.com/rss/",
    "https://36kr.com/feed",
    "https://www.huxiu.com/rss/0.xml",
    "https://www.tmtpost.com/rss",
    "https://www.ifanr.com/feed",
    "https://www.leikeji.com/rss",
    "https://www.mydrivers.com/rss.xml",
]

# 企业微信 Webhook
WECHAT_WEBHOOK = os.environ["WECHAT_WEBHOOK"]

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# 防止重复处理
processed_hashes = set()


def send_wechat(brand, summary, link, news_time):
    """
    发送企业微信消息，使用 Markdown 格式
    """
    message = f"""## 📱 {brand}

{summary}

发布时间: {news_time}
[🔗 点击查看原文]({link})
"""
    data = {
        "msgtype": "markdown",
        "markdown": {"content": message}
    }
    response = requests.post(WECHAT_WEBHOOK, json=data)
    if response.status_code != 200:
        print("企业微信发送失败:", response.text)


def summarize(content):
    """
    使用 DeepSeek API 生成新闻摘要
    """
    prompt = f"""
你是手机行业情报分析助手。
请输出：
1. 150字摘要
2. 分类：新品/供应链/财报/海外/组织/AI
3. 重要度 1-5（普通新闻1-2，重要发布3，战略级4-5）

新闻标题：
{content}
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.7
    }
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 402:
            print("DeepSeek API余额不足，请充值")
        else:
            print(f"DeepSeek API错误: {e}")
        return None


def is_today(published_struct):
    """
    判断 RSS 新闻是否是当天
    """
    if not published_struct:
        return False
    news_date = datetime(*published_struct[:6])
    today = datetime.now()
    return news_date.date() == today.date()


def process_news(brand, title, link, published_struct):
    """
    处理单条新闻：
    - 去重
    - 调用 DeepSeek 摘要
    - 重要度过滤
    - 推送企业微信
    """
    if not is_today(published_struct):
        return

    h = hashlib.md5(title.encode()).hexdigest()
    if h in processed_hashes:
        return
    processed_hashes.add(h)

    summary = summarize(title)
    if not summary:
        return

    # 简单重要度过滤
    if "重要度 1" in summary or "重要度 2" in summary or "重要度 3" in summary:
        return

    news_time = datetime(*published_struct[:6]).strftime("%Y-%m-%d %H:%M")
    send_wechat(brand, summary, link, news_time)
    print(f"已推送: {title} ({news_time})")


def fetch_google_news():
    """
    抓取 Google News RSS
    """
    for brand in BRANDS:
        url = f"https://news.google.com/rss/search?q={brand}+手机&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            process_news(brand, entry.title, entry.link, published_struct)


def fetch_media_news():
    """
    抓取其他科技媒体 RSS
    """
    for rss in MEDIA_RSS:
        feed = feedparser.parse(rss)
        for entry in feed.entries[:10]:
            published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            title = entry.title
            link = entry.link
            for brand in BRANDS:
                if brand in title:
                    process_news(brand, title, link, published_struct)


def main():
    fetch_google_news()
    fetch_media_news()


if __name__ == "__main__":
    main()
