# C:\Users\Wind\.gemini\config\skills\ai-morning-paper-publisher\scripts\publish_workflow.py
import os
import re
import sys
import json
import argparse
import requests
from pathlib import Path
from urllib.parse import urlparse

# 定义临时 HTML 文件落地路径
TEMP_HTML_PATH = Path(r"C:\Users\Wind\AppData\Local\Temp\ai_morning_paper_wechat_temp.html")

class WeChatWorkflow:
    def __init__(self):
        self.app_id, self.app_secret = self._load_credentials()
        self.base_url = "https://api.weixin.qq.com/cgi-bin"
        self.access_token = None

    def _load_credentials(self):
        # 1. 尝试从环境变量读取
        app_id = os.environ.get('WECHAT_APP_ID')
        app_secret = os.environ.get('WECHAT_APP_SECRET')
        if app_id and app_secret:
            return app_id, app_secret
            
        # 2. 尝试从本地 OpenClaw 配置读取
        config_path = Path(os.path.expanduser("~")) / ".stepclaw" / "openclaw.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    vars_dict = cfg.get("env", {}).get("vars", {})
                    return vars_dict.get("WECHAT_APP_ID"), vars_dict.get("WECHAT_APP_SECRET")
            except Exception:
                pass
        return None, None

    def get_public_ip(self):
        """阶段 1：获取公网 IP"""
        urls = ["https://api.ipify.org?format=json", "https://ifconfig.me/all.json"]
        ip = "未知"
        for url in urls:
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    ip = data.get("ip") or data.get("ip_addr")
                    if ip:
                        break
            except Exception:
                continue
        print(f"[IP_CHECK] 当前设备出口公网 IP: {ip}")
        print("[IP_CHECK] 请确保已将此 IP 填入微信公众平台 (基本配置 -> IP白名单) 中！")
        return ip

    def fetch_and_convert(self, url):
        """阶段 2：抓取公众号文章并转换为精美内联样式 HTML"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            print(f"[FETCH] 正在抓取原始文章: {url}")
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = 'utf-8'
            if "环境异常" in resp.text:
                print("[ERROR] 微信安全拦截：触发环境异常验证码，无法直接抓取")
                return False
                
            # 提取正文卡片
            card_pattern = r'<section class="news-card"[^>]*>(.*?)</section>'
            cards = re.findall(card_pattern, resp.text, re.DOTALL)
            if not cards:
                # 备用微信普通文章抓取正则
                content_match = re.search(r'id="js_content"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
                if content_match:
                    print("[INFO] 未匹配到早报专用卡片，降级抓取全文富文本...")
                    cards = [content_match.group(1)]
                else:
                    print("[ERROR] 未在页面中找到合法的文章正文结构")
                    return False

            # 高级排版转换
            card_style = (
                "background-color: #FFFFFF; border: 1px solid rgba(0, 0, 0, 0.06); "
                "border-radius: 16px; padding: 24px; margin-bottom: 24px; position: relative; "
                "box-shadow: 0 10px 25px rgba(0, 0, 0, 0.03); font-family: -apple-system, sans-serif;"
            )
            
            wechat_html = '<div style="background-color: #FAFAFA; padding: 20px 15px; color: #1F2937;">'
            # 头部大标题
            wechat_html += (
                '<div style="text-align: center; margin-bottom: 35px; padding: 25px 0; border-bottom: 1px solid rgba(0,0,0,0.06);">'
                '<div style="display: inline-block; background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(168, 85, 247, 0.08) 100%); border: 1px solid rgba(99, 102, 241, 0.15); border-radius: 30px; padding: 4px 16px; margin-bottom: 12px;">'
                '<span style="color: #6366F1; font-size: 11px; font-weight: bold; letter-spacing: 0.1em;">DAILY INTELLIGENCE</span>'
                '</div>'
                '<h1 style="font-size: 28px; font-weight: 800; color: #111827; margin: 5px 0 10px 0;">AI 行业前沿早报</h1>'
                '<p style="color: #4B5563; font-size: 14px; font-weight: 500;">每日 AI 行业前沿资讯聚合</p>'
                '<div style="width: 60px; height: 3px; background: linear-gradient(to right, #6366F1, #A855F7); margin: 20px auto 0 auto; border-radius: 2px;"></div>'
                '</div>'
            )

            for index, card_content in enumerate(cards, start=1):
                num_str = f"{index:02d}"
                badge = f'<span style="background: linear-gradient(135deg, #6366F1 0%, #A855F7 100%); color: #FFFFFF; font-size: 10px; padding: 3px 8px; border-radius: 4px 12px 4px 12px; font-weight: bold; margin-bottom: 15px; display: inline-block;">NEWS #{num_str}</span>'
                
                # 清洗标签
                card_content = re.sub(r'<h2 class="card-title">(.*?)</h2>', r'<h2 style="font-size: 19px; font-weight: 700; color: #111827; margin-bottom: 12px; line-height: 1.4;">\1</h2>', card_content)
                card_content = re.sub(r'<span class="card-tag">(.*?)</span>', r'<span style="background-color: rgba(99, 102, 241, 0.05); border: 1px solid rgba(99, 102, 241, 0.15); color: #6366F1; font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 15px;">\1</span>', card_content)
                card_content = re.sub(r'<p class="lead-paragraph">(.*?)</p>', r'<p style="color: #1F2937; font-size: 15px; line-height: 1.65; font-weight: 500; border-bottom: 1px dashed rgba(0,0,0,0.06); padding-bottom: 14px; margin-bottom: 14px;">\1</p>', card_content)
                card_content = re.sub(r'<p class="detail-paragraph">(.*?)</p>', r'<div style="border-left: 2px solid rgba(99, 102, 241, 0.4); padding-left: 12px; margin-bottom: 14px;"><p style="color: #4B5563; font-size: 14px; line-height: 1.6; margin: 0;">\1</p></div>', card_content)
                
                # 剔除 SVG 与过滤超链接
                card_content = re.sub(r'<svg[^>]*>.*?</svg>', '', card_content, flags=re.DOTALL)
                card_content = re.sub(r'<a href="([^"]+)"[^>]*>.*?</a>', r'<span style="color: #9CA3AF; font-size: 12px; display: block; margin-top: 15px; border-top: 1px solid rgba(0,0,0,0.05); padding-top: 12px;">来源: \1</span>', card_content, flags=re.DOTALL)
                
                # 剔除冗余 div 容器
                card_content = re.sub(r'<div class="card-footer">', '', card_content)
                card_content = re.sub(r'<div class="card-header">', '', card_content)
                card_content = re.sub(r'<div class="card-body">', '', card_content)
                card_content = card_content.replace('</div>', '')
                
                wechat_html += f'<section style="{card_style}">{badge}\n{card_content}</section>\n'

            wechat_html += '</div>'
            
            # 写入临时文件
            TEMP_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TEMP_HTML_PATH, "w", encoding="utf-8") as f:
                f.write(wechat_html)
            print(f"[SUCCESS] 转换完成，微信专属 HTML 临时保存在: {TEMP_HTML_PATH}")
            return True
        except Exception as e:
            print(f"[ERROR] 转换流程失败: {e}")
            return False

    def push_draft(self, title, cover_path, author="", digest=""):
        """阶段 3：推送草稿箱"""
        if not self.app_id or not self.app_secret:
            print("[ERROR] 微信凭证缺失，请设置 WECHAT_APP_ID 和 WECHAT_APP_SECRET")
            return False
            
        if not TEMP_HTML_PATH.exists():
            print(f"[ERROR] 未找到待推送的临时 HTML 文件: {TEMP_HTML_PATH}，请先执行 convert 阶段！")
            return False

        # 1. 获取 access_token
        url = f"{self.base_url}/token"
        params = {"grant_type": "client_credential", "appid": self.app_id, "secret": self.app_secret}
        try:
            resp = requests.get(url, params=params, timeout=10).json()
            if "access_token" in resp:
                self.access_token = resp["access_token"]
            else:
                print(f"[ERROR] 获取 Token 失败: {resp.get('errmsg')}")
                return False
        except Exception as e:
            print(f"[ERROR] 连通微信服务器失败: {e}")
            return False

        # 2. 上传封面图
        print(f"[UPLOAD] 正在上传封面图: {cover_path}")
        cover_file = Path(cover_path)
        if not cover_file.exists():
            print(f"[ERROR] 封面图文件未找到: {cover_path}")
            return False
            
        url = f"{self.base_url}/material/add_material?access_token={self.access_token}&type=image"
        try:
            with open(cover_file, 'rb') as f:
                files = {"media": (cover_file.name, f.read(), "image/jpeg")}
                upload_res = requests.post(url, files=files, timeout=30).json()
            if "media_id" in upload_res:
                thumb_media_id = upload_res["media_id"]
                print(f"[OK] 封面图上传成功, media_id: {thumb_media_id}")
            else:
                print(f"[ERROR] 封面图上传失败: {upload_res}")
                return False
        except Exception as e:
            print(f"[ERROR] 图片上传异常: {e}")
            return False

        # 3. 创建草稿
        with open(TEMP_HTML_PATH, "r", encoding="utf-8") as f:
            content_html = f.read()

        url = f"{self.base_url}/draft/add?access_token={self.access_token}"
        data = {
            "articles": [{
                "title": title,
                "author": author,
                "digest": digest or "每日 AI 行业前沿资讯聚合",
                "content": content_html,
                "thumb_media_id": thumb_media_id,
                "show_cover_pic": 1,
                "need_open_comment": 0,
                "only_fans_can_comment": 0
            }]
        }
        
        try:
            headers = {'Content-Type': 'application/json; charset=utf-8'}
            payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
            res = requests.post(url, data=payload, headers=headers, timeout=30).json()
            if "media_id" in res:
                print(f"\n[SUCCESS] 公众号草稿发布成功!")
                print(f"[INFO] Draft Media ID: {res['media_id']}")
                return True
            else:
                print(f"[ERROR] 草稿发布失败: {res}")
                return False
        except Exception as e:
            print(f"[ERROR] 推送请求异常: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="AI 早报微信公众号一键推送工作流")
    parser.add_argument("--stage", required=True, choices=["get-ip", "convert", "push"], help="执行阶段")
    parser.add_argument("--url", help="[convert 阶段] 原始早报微信链接")
    parser.add_argument("--title", help="[push 阶段] 公众号文章标题")
    parser.add_argument("--cover", help="[push 阶段] 封面图文件路径")
    parser.add_argument("--author", default="", help="[push 阶段] 作者署名")
    parser.add_argument("--digest", help="[push 阶段] 摘要")
    
    args = parser.parse_args()
    wf = WeChatWorkflow()
    
    if args.stage == "get-ip":
        wf.get_public_ip()
    elif args.stage == "convert":
        if not args.url:
            print("[ERROR] 执行 convert 阶段必须提供 --url 参数！")
            sys.exit(1)
        success = wf.fetch_and_convert(args.url)
        sys.exit(0 if success else 1)
    elif args.stage == "push":
        if not args.title or not args.cover:
            print("[ERROR] 执行 push 阶段必须提供 --title 和 --cover 参数！")
            sys.exit(1)
        success = wf.push_draft(args.title, args.cover, args.author, args.digest)
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
