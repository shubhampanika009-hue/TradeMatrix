[app]
title = TradeMatrix
package.name = tradematrix
package.domain = org.tradematrix
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,html,js,css
version = 0.1

# Kivy और आवश्यक डिपेंडेंसी को स्पष्ट रूप से निर्दिष्ट करें:
requirements = python3,kivy==2.3.0,kivymd,requests,urllib3

orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 21
