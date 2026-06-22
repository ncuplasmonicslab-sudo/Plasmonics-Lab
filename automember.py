import os
import json

def generate_members_json(base_path="images/former-members",filename="former-members.json"):
    # 存放所有分類與成員的字典
    members_data = {}

    # 掃描所有分類 (phd, master, undergraduate)
    for category in os.listdir(base_path):
        category_path = os.path.join(base_path, category)
        
        # 確保是資料夾
        if os.path.isdir(category_path):
            members_data[category] = []  # 初始化分類的成員清單

            # 掃描該分類下的所有成員資料夾
            for member in os.listdir(category_path):
                member_path = os.path.join(category_path, member)
                
                # 確保是資料夾
                if os.path.isdir(member_path):
                    members_data[category].append(member)

    # 將結果儲存為 JSON 檔案
    with open(filename, "w", encoding="utf-8") as json_file:
        json.dump(members_data, json_file, indent=4)
    
    print("✅ former-members.json 已成功生成！")

# 執行腳本
generate_members_json(base_path="images/former-members",filename="former-members.json")
generate_members_json(base_path="images/current-members",filename="current-members.json")