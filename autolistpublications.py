import requests
from googleapiclient.discovery import build

def search_images_google(api_key, cse_id, query, num=1):
    service = build("customsearch", "v1", developerKey=api_key)
    res = service.cse().list(
        q=query,
        cx=cse_id,
        searchType='image',
        num=num,
        # imgType='photo',  # 可以嘗試移除或改變
        safe='off'  # 根據需要調整
    ).execute()
    
    image_urls = []
    if 'items' in res:
        for item in res['items']:
            image_urls.append(item['link'])
    return image_urls

api_key = "AIzaSyBe27QscIQZSM-7f_extUsUhg2Qe3LL_wo" #google json search api https://developers.google.com/custom-search/v1/overview?hl=zh-tw
cse_id = "92d11a3333a704dd6"                        #https://programmablesearchengine.google.com/controlpanel/all

url = 'https://scholars.ncu.edu.tw/zh/persons/bor-kae-chang/publications/'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
html_content = response.text
from bs4 import BeautifulSoup

soup = BeautifulSoup(html_content, 'html.parser')
publications = []

# 查找所有包含文章信息的元素
for item in soup.find_all('li', class_='list-result-item'):
    # 提取标题
    title_tag = item.find('h3', class_='title')
    title = title_tag.get_text(strip=True) if title_tag else 'N/A'

    # 提取文章链接
    url_tag = title_tag.find('a', href=True) if title_tag else None
    url = url_tag['href'] if url_tag else 'N/A'

    # 提取作者信息
    #author_tags = item.find_all('a', class_='Person')
    #authors = [author.get_text(strip=True) for author in author_tags]
    authors_text = item.get_text()
    # 使用正則表達式或分割方式提取作者
    import re
    authors = re.findall(r'[A-Z][a-z]+, [A-Z]\. [A-Z]\.', authors_text)

    # 提取期刊名称
    journal_tag = item.find('span', class_='journal')
    journal = journal_tag.get_text(strip=True).replace('於: ', '').strip('.')[2:] if journal_tag else item.find('em').get_text(strip=True)



    # 擷取年份
    date_tag = item.find('span', class_='date')
    year = date_tag.get_text()[-8::] if date_tag else "Not Found"

    # 提取关键词
    keyword_tags = item.find_all('button', class_='concept-badge-small')
    keywords = [keyword.get_text(strip=True)[:-4] for keyword in keyword_tags]
    
    urls = search_images_google(api_key, cse_id, title, num=0)
    # 构建文章信息字典
    publication = {
        'title': title,
        'authors': authors,
        'journal': journal,
        'url': url,
        'year': year,
        'img_scr': urls,
        'keywords': keywords
    }
    publications.append(publication)
import json

with open('publications_日本人.json', 'w', encoding='utf-8') as f:
    json.dump(publications, f, ensure_ascii=False, indent=4)