import asyncio
import os
import time
from datetime import datetime

import discord
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# .envファイルの読み込み
load_dotenv()


async def main():
    # 環境変数の読み込みを確認
    email = os.environ["DMM_EMAIL"]
    password = os.environ["DMM_PASSWORD"]
    sheet_url = os.environ["DMM_GOOGLE_SHEET_URL"]

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )  # 今日の日付を取得（ファイル名に入れるため）
    login_url = "https://accounts.dmm.co.jp/service/login/password/=/path=SgVTFksZDEtUDFNKUkQfGA__"
    count = 0

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=chrome_options)

    dmm_login = DMMLogin(driver, login_url, email, password)
    dmm_login.login()  # ログイン関数の実行

    dmm_library = DMMLibrary(driver)  # initにdriverを渡す
    dmm_library.navigate_to_library()
    data = dmm_library.scroll_and_collect_data()  # 取得した値をdataに格納
    driver.quit()

    google_spreadsheet = GoogleSpreadsheet(
        sheet_url
    )  # クラスに値を渡す、initに渡すものがない場合は空でOK
    count = google_spreadsheet.write_data(data, count)  # countを戻り値として受け取る
    google_spreadsheet.AutoFilter(data)

    token = os.environ["DISCORD_TOKEN"]  # トークンを環境変数などから取得するのがベスト
    discord_bot = DiscordBOT(token)
    discord_bot.run(sheet_url)  # メッセージを送信し、Botを実行します


class DMMLogin:
    def __init__(self, driver, login_url, email, password):
        self.driver = driver
        self.login_url = login_url
        self.email = email
        self.password = password

    def login(self):
        self.driver.get(self.login_url)
        self.driver.set_window_size(1000, 1000)  # ウィンドウサイズを指定
        time.sleep(10)

        try:
            name_box = self.driver.find_element(By.NAME, "login_id")
            name_box.send_keys(self.email)
            print("ユーザー名入力完了")
        except Exception as e:
            print(f"ユーザー名入力フィールドが見つかりません: {e}")

        try:
            pass_box = self.driver.find_element(By.NAME, "password")
            pass_box.send_keys(self.password)
            print("パスワード入力完了")
        except Exception as e:
            print(f"パスワード入力フィールドが見つかりません: {e}")

        try:
            time.sleep(3)
            login_button = self.driver.find_element(
                By.XPATH, '//button[text()="ログイン"]'
            )
            self.driver.execute_script("arguments[0].click();", login_button)
            print("フォームを送信しました")
        except Exception as e:
            print(f"フォームの送信に失敗しました: {e}")

        print("ログイン完了")


class DMMLibrary:
    def __init__(self, driver):
        self.driver = driver

    def navigate_to_library(self):
        time.sleep(3)
        self.driver.get("https://www.dmm.co.jp/dc/-/mylibrary/")
        try:
            time.sleep(3)
            yes_button = self.driver.find_element(
                By.XPATH, "//a[contains(@href, 'declared=yes')]"
            )
            yes_button.click()
            print("「はい」をクリックしました")
        except Exception as e:
            print(f"「はい」が見つかりません: {e}")
        time.sleep(4)

    def scroll_and_collect_data(self):
        try:
            svg_path = self.driver.find_element(
                By.XPATH, "//*[@class='silex-element-content']"
            )
            svg_path.click()
        except Exception as e:
            print(f"「×」が見つかりません")

        actions = self.driver.find_element(By.CLASS_NAME, "purchasedListArea1Znew")
        previous_scroll_height = 0

        while True:
            current_scroll_height = self.driver.execute_script(
                "return arguments[0].scrollTop + arguments[0].clientHeight;", actions
            )
            self.driver.execute_script(
                "arguments[0].scrollTop += arguments[0].clientHeight;", actions
            )
            time.sleep(1)
            new_scroll_height = self.driver.execute_script(
                "return arguments[0].scrollTop + arguments[0].clientHeight;", actions
            )
            if new_scroll_height == current_scroll_height:
                break

        titles = self.driver.find_elements(By.CLASS_NAME, "productTitle3sdi8")
        circles = self.driver.find_elements(By.CLASS_NAME, "circleName209pI")
        kinds = self.driver.find_elements(By.CLASS_NAME, "default3EHgn")

        length = min(len(titles), len(circles), len(kinds))
        data = [(titles[i].text, circles[i].text, kinds[i].text) for i in range(length)]

        return data


class GoogleSpreadsheet:
    def __init__(self, sheet_url):
        self.scope = ["https://spreadsheets.google.com/feeds"]
        self.creds = Credentials.from_service_account_file(
            "service_token.json", scopes=self.scope
        )
        self.client = build("sheets", "v4", credentials=self.creds)
        self.sheet_url = sheet_url

    def write_data(self, data, count):
        spreadsheet = (
            self.client.spreadsheets().get(spreadsheetId=self.sheet_url).execute()
        )
        sheet_name = spreadsheet["sheets"][0]["properties"]["title"]

        self.client.spreadsheets().values().clear(
            spreadsheetId=self.sheet_url, range=f"{sheet_name}!A:Z"
        )

        all_data = [["タイトル", "サークル", "種類"]] + data
        body = {"values": all_data}

        result = (
            self.client.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.sheet_url,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body=body,
            )
            .execute()
        )

        count += len(data)
        print(f"{count}件のデータを書き込みました")
        return count

    def AutoFilter(self, data):
        # シートの情報を取得
        spreadsheet = (
            self.client.spreadsheets().get(spreadsheetId=self.sheet_url).execute()
        )
        sheet_name = spreadsheet["sheets"][0]["properties"]["title"]

        # 最終列の計算（data の最初の要素の長さで判断）
        last_column_num = len(data[0]) if data else 3
        print(f"最終列は{last_column_num}です")

        # 列番号をアルファベットに変換
        def num2alpha(num):
            if num <= 26:
                return chr(64 + num)
            elif num % 26 == 0:
                return num2alpha(num // 26 - 1) + chr(90)
            else:
                return num2alpha(num // 26) + chr(64 + num % 26)

        last_column_alp = num2alpha(last_column_num)
        print(f"最終列のアルファベットは{last_column_alp}です")

        # フィルターを設定
        requests = [
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": spreadsheet["sheets"][0]["properties"][
                                "sheetId"
                            ],
                            "startRowIndex": 0,
                            "endRowIndex": len(data)
                            + 1,  # 行数の指定（ヘッダー行を含むため +1）
                            "startColumnIndex": 0,
                            "endColumnIndex": last_column_num,
                        }
                    }
                }
            }
        ]

        body = {"requests": requests}

        self.client.spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_url, body=body
        ).execute()
        print("フィルターを設定しました")


class DiscordBOT:
    def __init__(self, token):
        self.token = token
        self.channel_id = "1279064814697713664"

        # Intents を設定
        self.intents = discord.Intents.default()
        self.intents.message_content = True  # メッセージの内容を受け取るための設定

        self.bot = discord.Client(intents=self.intents)

        # イベントハンドラーを設定
        self.bot.event(self.on_ready)

    # 非同期関数として on_ready を定義
    async def on_ready(self):
        print(f"Logged in as {self.bot.user} (ID: {self.bot.user.id})")
        await self.send_message(
            f"DMMの購入リストを取得、書き込みました:\nhttps://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
        )
        await self.bot.close()  # ボットを終了する

    async def send_message(self, message):
        channel = self.bot.get_channel(int(self.channel_id))
        if channel:
            await channel.send(message)
            print("メッセージを送信しました")
        else:
            print("チャンネルが見つかりませんでした")

    async def run(self, sheet_url):
        self.spreadsheet_id = sheet_url
        await self.bot.start(self.token)  # 非同期処理としてボットを開始


if __name__ == "__main__":
    asyncio.run(main())
