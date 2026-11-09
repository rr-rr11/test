"""
اجرا روی کامپیوتر خودتان (نه در GitHub):
    python save_session.py
مرورگر باز می‌شود؛ با گوگل وارد RollerCoin شوید، بعد در ترمینال Enter بزنید.
خروجی در فایل session.txt ذخیره می‌شود؛ محتوایش را در GitHub Secret به نام RC_SESSION بگذارید.
⚠️ این فایل مثل رمز عبور است؛ به کسی ندهید و commit نکنید.
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import export_session

opts = Options()
opts.add_argument("--window-size=1200,900")
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
try:
    d.get("https://rollercoin.com/signin")
    input("با گوگل لاگین کنید تا وارد حساب شوید، سپس اینجا Enter بزنید... ")
    blob = export_session(d)
    open("session.txt", "w").write(blob)
    print(f"ذخیره شد: session.txt ({len(blob)} کاراکتر)")
finally:
    d.quit()
