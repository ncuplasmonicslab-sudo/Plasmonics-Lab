import requests

url = 'https://scholars.ncu.edu.tw/en/persons/chih-ming-wang/projects/'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
response.raise_for_status()  # 确保请求成功
html_content = response.text
from bs4 import BeautifulSoup
import json
from datetime import datetime

soup = BeautifulSoup(html_content, 'html.parser')
projects = []

# 查找所有项目的容器
project_containers = soup.find_all('div', class_='rendering_upmproject')

for container in project_containers:
    # 提取项目名称和链接
    title_tag = container.find('h3', class_='title')
    if title_tag and title_tag.a:
        title = title_tag.get_text(strip=True)
        link = title_tag.a['href']
        # 如果链接是相对路径，转换为绝对路径
        if link.startswith('/'):
            link = 'https://scholars.ncu.edu.tw' + link
    else:
        title = 'N/A'
        link = 'N/A'

    # 提取执行日期
    date_tags = container.find_all('span', class_='date')
    if date_tags and len(date_tags) == 2:
        start_date = date_tags[0].get_text(strip=True)
        end_date = date_tags[1].get_text(strip=True)
    else:
        start_date = end_date = 'N/A'

    # 格式化日期
    def format_date(date_str):
        try:
            # 解析日期字符串，假设格式为 'd/m/y'
            date_obj = datetime.strptime(date_str, '%d/%m/%y')
            # 格式化为标准日期格式，例如：2023-09-01
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            return date_str  # 如果解析失败，返回原始字符串

    start_date = format_date(start_date)
    end_date = format_date(end_date)

    # 将项目信息添加到列表
    projects.append({
        'title': title,
        'start_date': start_date,
        'end_date': end_date,
        'url': link
    })

# 将结果保存为 JSON 文件
with open('projects.json', 'w', encoding='utf-8') as f:
    json.dump(projects, f, ensure_ascii=False, indent=4)
