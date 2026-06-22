from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# 設定 ChromeDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # 啟動無頭模式，不開啟瀏覽器視窗
options.add_argument("--disable-blink-features=AutomationControlled")  # 避免被識破
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")

# 啟動瀏覽器
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# 開啟網頁
url = "https://scholars.ncu.edu.tw/zh/publications/broadband-achromatic-thermal-metalens-with-a-wide-field-of-view-b"
driver.get(url)

# 查找所有 class='doi' 的超連結
doi_links = [elem.get_attribute("href") for elem in driver.find_elements(By.CLASS_NAME, "doi")]

# 輸出結果
if doi_links:
    print("找到的 DOI 連結：")
    for link in doi_links:
        print(link)
else:
    print("未找到任何 DOI 連結。")

# 關閉瀏覽器
driver.quit()
