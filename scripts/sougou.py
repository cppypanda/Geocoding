import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime
import time
import urllib.parse

print(f"\n程序开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

#首先设置一下搜索关键词
keyword = "福建省莆田市宋城"
#搜狗搜索每页显示10条结果
result_per_page = 10
total_result = 10
 
page_got = 0
num = 0
 
data = []
 
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
}

def fix_weixin_url(url):
    """修复微信文章URL"""
    try:
        if 'mp.weixin.qq.com' in url:
            # 如果是完整的URL，直接返回
            if url.startswith('http'):
                return url
            # 如果是相对路径，添加域名
            elif url.startswith('//'):
                return 'https:' + url
            # 如果URL被搜狗修改过，提取原始参数
            elif 'url=' in url:
                parsed = urllib.parse.urlparse(url)
                query_params = urllib.parse.parse_qs(parsed.query)
                if 'url' in query_params:
                    return query_params['url'][0]
            # 其他情况，添加域名
            return 'https://mp.weixin.qq.com' + url
        return url
    except Exception as e:
        print(f"    修复微信链接失败: {e}")
        return url

def get_article_content(url):
    try:
        print(f"    正在获取文章内容...")
        
        # 处理微信文章
        if 'mp.weixin.qq.com' in url:
            headers_weixin = headers.copy()
            headers_weixin.update({
                'Host': 'mp.weixin.qq.com',
                'Referer': 'https://mp.weixin.qq.com/'
            })
            response = requests.get(url, headers=headers_weixin, timeout=15)
            # 微信文章强制使用UTF-8编码
            response.encoding = 'utf-8'
        else:
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = response.apparent_encoding
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 移除script、style和iframe标签
        for tag in soup(['script', 'style', 'iframe']):
            tag.decompose()
            
        # 根据不同网站提取内容
        content = ""
        
        # 微信公众号文章
        if 'mp.weixin.qq.com' in url:
            # 尝试不同的选择器
            article = (
                soup.find('div', id='js_content') or  # 新版文章内容
                soup.find('div', class_='rich_media_content') or  # 富媒体内容
                soup.find('div', id='content_html') or  # 内容HTML
                soup.find('div', class_='wx_content')  # 微信内容
            )
            if article:
                # 获取所有段落
                paragraphs = article.find_all(['p', 'section'])
                texts = []
                for p in paragraphs:
                    # 处理每个段落的文本
                    text = p.get_text(strip=True)
                    # 检查是否包含乱码（检查常见的乱码特征）
                    if not re.search(r'[\uFFFD\u0000-\u001F]', text) and len(text) > 10:
                        texts.append(text)
                if texts:
                    content = '\n'.join(texts)
            
            # 如果上述方法失败，尝试其他方法
            if not content:
                # 查找最长的文本块
                text_blocks = []
                for tag in soup.find_all(['div', 'section']):
                    text = tag.get_text(strip=True)
                    # 过滤掉包含乱码的文本块
                    if not re.search(r'[\uFFFD\u0000-\u001F]', text) and len(text) > 100:
                        text_blocks.append(text)
                if text_blocks:
                    content = max(text_blocks, key=len)
                    
            # 如果内容为空或疑似乱码，尝试使用不同的编码重新获取
            if not content or re.search(r'[\uFFFD\u0000-\u001F]', content):
                for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                    try:
                        response = requests.get(url, headers=headers_weixin, timeout=15)
                        response.encoding = encoding
                        soup = BeautifulSoup(response.text, 'html.parser')
                        article = soup.find('div', id='js_content')
                        if article:
                            text = article.get_text(strip=True)
                            if not re.search(r'[\uFFFD\u0000-\u001F]', text):
                                content = text
                                break
                    except:
                        continue
        
        # 政府网站规则
        elif any(domain in url.lower() for domain in ['gov.cn', 'government']):
            # 常见的政府网站文章容器类名和ID
            possible_selectors = [
                'div.article-con',  # 衡阳政府网
                'div.TRS_Editor',   # 常见政府网站编辑器
                'div.article',      # 通用文章容器
                'div.content',      # 通用内容容器
                'div.article-content', # 文章内容
                'div#zoom',         # 很多政府网站使用
                'div.news_content', # 新闻内容
                'div.zwxl-article', # 政务信息文章
                'div.content-box',  # 内容盒子
                'div.detail-content', # 详情内容
                'div#UCAP-CONTENT', # 统一内容访问平台
                'div.info-cont',    # 信息内容
                'div.wzy_content',  # 文章正文内容
                'div.document-content', # 文档内容
                '#mainText',        # 主要文本
            ]
            
            # 尝试所有可能的选择器
            for selector in possible_selectors:
                article = soup.select_one(selector)
                if article:
                    # 获取所有段落文本
                    paragraphs = article.find_all(['p', 'div', 'span', 'td'])
                    texts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 10:  # 过滤掉太短的段落
                            texts.append(text)
                    if texts:
                        content = '\n'.join(texts)
                        break
            
            # 如果上述选择器都没找到内容，尝试其他方法
            if not content:
                # 寻找最长的文本块
                text_blocks = []
                for tag in soup.find_all(['div', 'article', 'section']):
                    text = tag.get_text(strip=True)
                    if len(text) > 100:  # 只考虑较长的文本块
                        text_blocks.append(text)
                if text_blocks:
                    content = max(text_blocks, key=len)
        
        elif 'sohu.com' in url:
            # 搜狐网站
            article = soup.find('article')
            if article:
                content = article.get_text(strip=True)
        elif 'toutiao.com' in url:
            # 今日头条
            article = soup.find('article') or soup.find('div', class_='article-content')
            if article:
                content = article.get_text(strip=True)
        else:
            # 通用提取方法
            article = (
                soup.find('article') or 
                soup.find('div', class_=re.compile(r'article|content|text|main', re.I)) or
                soup.find('div', id=re.compile(r'article|content|text|main', re.I))
            )
            if article:
                content = article.get_text(strip=True)
            else:
                # 如果找不到特定容器，提取body中的所有文本
                content = soup.body.get_text(strip=True) if soup.body else ""
        
        # 清理文本
        if content:
            # 删除多余空白字符
            content = re.sub(r'\s+', ' ', content)
            # 删除特殊字符
            content = re.sub(r'[\r\n\t]', '', content)
            # 检查并修复可能的编码问题
            if re.search(r'[\uFFFD\u0000-\u001F]', content):
                content = content.encode('utf-8', 'ignore').decode('utf-8')
            # 限制内容长度
            content = content[:2000] if len(content) > 2000 else content
            
        print(f"    成功获取文章内容，长度：{len(content)}字符")
        return content
    except Exception as e:
        print(f"    获取文章内容失败: {e}")
        return "获取文章内容失败"

def get_real_url(sogou_url):
    try:
        print(f"    正在获取真实链接...")
        
        # 处理微信文章链接
        if 'weixin.qq.com' in sogou_url or 'mp.weixin.qq.com' in sogou_url:
            fixed_url = fix_weixin_url(sogou_url)
            print(f"    修复后的微信链接: {fixed_url}")
            return fixed_url
            
        # 添加域名前缀
        if sogou_url.startswith('/'):
            full_url = f"https://www.sogou.com{sogou_url}"
        else:
            full_url = sogou_url
            
        # 发送HEAD请求检查重定向
        response = requests.head(full_url, headers=headers, allow_redirects=False)
        if response.status_code == 302 or response.status_code == 301:
            real_url = response.headers.get('Location', '')
        else:
            # 如果没有立即重定向，尝试GET请求
            response = requests.get(full_url, headers=headers, allow_redirects=False)
            if response.status_code == 302 or response.status_code == 301:
                real_url = response.headers.get('Location', '')
            else:
                # 尝试从页面内容中提取真实URL
                match = re.search(r"window\.location\.replace\([\"\'](.*?)[\"\']", response.text)
                if match:
                    real_url = match.group(1)
                else:
                    real_url = "无法获取真实链接"
        
        print(f"    真实链接是: {real_url}")
        return real_url
    except Exception as e:
        print(f"    获取真实URL失败: {e}")
        return "获取真实链接失败"
 
while page_got < total_result:
    try:
        # 搜狗搜索的URL格式
        url = f"https://www.sogou.com/web?query={keyword}&page={num + 1}"
        
        print(f"\n开始获取第 {num + 1} 页的数据...")
        print(f"当前页面URL: {url}")
        
        print("正在发送请求...")
        response = requests.get(url, headers=headers)
        response.encoding = "utf-8"
        print("请求成功，开始解析页面...")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # 搜狗搜索结果的容器
        results = soup.find_all('div', class_='vrwrap')
        
        print(f"在当前页面找到 {len(results)} 条搜索结果")
     
        for idx, result in enumerate(results, 1):
            try:
                print(f"\n  处理第 {idx}/{len(results)} 条结果...")
                
                # 查找标题
                title_elem = result.find('h3', class_='vr-title').find('a')
                title = title_elem.text.strip() if title_elem else "未找到标题"
                print(f"  标题: {title}")
                
                # 获取链接
                link = title_elem['href'] if title_elem else None
                if not link:
                    print("  未找到链接，跳过此结果")
                    continue
                print(f"  搜狗链接: {link}")
                
                # 获取真实链接
                real_link = get_real_url(link)
                if not real_link or real_link.startswith("获取真实链接失败"):
                    real_link = "获取真实链接失败"
                    article_content = "无法获取文章内容"
                else:
                    # 获取文章内容
                    article_content = get_article_content(real_link)
                    # 添加延时避免请求过快
                    time.sleep(2)
                
                # 获取来源网站
                source_elem = result.find('div', class_='citeurl')
                source_site = source_elem.text.strip() if source_elem else "未知来源"
                print(f"  来源网站: {source_site}")
                
                # 获取简介
                desc_elem = result.find('div', class_='text-layout')
                desc = desc_elem.text.strip() if desc_elem else "未找到简介"
                print(f"  简介长度: {len(desc)} 字符")
     
                data.append({
                    '标题': title,
                    '搜狗链接': link,
                    '真实链接': real_link,
                    '简介': desc,
                    '来源网站': source_site,
                    '文章内容': article_content
                })
                
                page_got += 1
                print(f"  已成功获取 {page_got}/{total_result} 条数据")
                
                if page_got >= total_result:
                    break
            except Exception as e:
                print(f"  处理单条结果时出错: {e}")
                continue
                
        if page_got >= total_result:
            break
            
    except Exception as e:
        print(f"处理页面时出错: {e}")
        break
        
    num += 1

print("\n爬取完成")
print(f"共获取 {len(data)} 条结果")
df = pd.DataFrame(data)
output_file = f"搜狗爬取结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
df.to_excel(output_file, index=False)
print(f"结果已保存到 {output_file}")