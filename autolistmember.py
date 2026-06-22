import pandas as pd

# 讀取上傳的 Excel 檔案
file_path = 'C:/Users/CYY/Downloads/收集個人資料作為建立實驗室網站用 (回覆).xlsx'
df = pd.read_excel(file_path)

# 將每位成員的資料整理成 JSON 格式
json_list = []

for _, row in df.iterrows():
    json_list.append({
        "name_zh": row['name_zh'],
        "name_en": row['name_en'],
        "year_of_enrollment_zh": row['year_of_enrollment_zh'],
        "year_of_enrollment_en": row['year_of_enrollment_en'],
        "degree_zh": row['degree_zh'],
        "degree_en": row['degree_en'],
        "graduated": row['graduated'] == "是",  # 轉換成布林值
        "school_zh": row['school_zh'],
        "school_en": row['school_en'],
        "skills_zh": row['skills_zh'],
        "skills_en": row['skills_en'],
        "research_interests_zh": row['research_interests_zh'],
        "research_interests_en": row['research_interests_en'],
        "email": row['email'],
        "current_employment_zh": row['current_employment_zh'],
        "current_employment_en": row['current_employment_en'],
        "url": f"images/member/{row['name_zh']}.jpg"
    })

import json

# 將結果轉換為 JSON 格式並儲存
json_output_path = '成員資料.json'
with open(json_output_path, 'w', encoding='utf-8') as f:
    json.dump(json_list, f, ensure_ascii=False, indent=4)