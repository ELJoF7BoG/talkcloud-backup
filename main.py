import os
import requests
import json
import time
import shutil
import threading
import glob
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import re  # 파일명 정리를 위해 추가
from datetime import datetime  # 날짜/시간 변환을 위해 추가
import csv  # CSV 파일 생성을 위해 추가

class TalkDriveUnifiedBackupApp:
    
    # --- API 설정 ---
    # 각 백업 유형에 맞는 API 주소와 페이징 방식을 정의
    API_CONFIG = {
        "MEDIA": {
            "base_url": "https://drawer-api.kakao.com/mediaFile/list?verticalType=MEDIA&fetchCount=100&joined=true&direction=DESC",
            "log_suffix": "_list.json",
            "folder_name": "Photo_Backup"
        },
        "FILE": {
            "base_url": "https://drawer-api.kakao.com/mediaFile/list?verticalType=FILE&fetchCount=100&joined=true&direction=DESC",
            "log_suffix": "_list.json",
            "folder_name": "File_Backup"
        },
        "LINK": {
            "base_url": "https://drawer-api.kakao.com/link/list?verticalType=LINK&fetchCount=100&joined=true&direction=DESC",
            "log_suffix": "_link_list.json",
            "folder_name": "Link_Backup"
        }
    }
    
    REQ_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/5.36',
        'Accept': 'application/json+javascript'
    }
    THREADS_COUNT = 5

    def __init__(self, root):
        self.root = root
        self.root.title("카카오톡 톡클라우드 통합 백업")
        self.root.geometry("700x550") # 높이 약간 늘림

        self.cookies = {}
        self.backup_folder = tk.StringVar()
        self.cookie_folder = tk.StringVar()
        
        # 중지 플래그 (threading.Event는 스레드 간 안전하게 신호를 공유)
        self.stop_requested = threading.Event()
        
        self.cookie_folder.set(os.path.abspath(os.getcwd()))

        # --- GUI 위젯 생성 ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 쿠키 폴더 설정
        cookie_frame = ttk.LabelFrame(main_frame, text=" 1. 쿠키 파일 경로 (talkcloud.kakao.com_cookies.txt가 있는 폴더) ")
        cookie_frame.pack(fill=tk.X, padx=5, pady=5)
        
        cookie_entry = ttk.Entry(cookie_frame, textvariable=self.cookie_folder, width=70)
        cookie_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        
        cookie_button = ttk.Button(cookie_frame, text="찾아보기", command=self.select_cookie_folder)
        cookie_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # 2. 백업 저장 폴더 설정
        backup_frame = ttk.LabelFrame(main_frame, text=" 2. 메인 백업 저장 경로 (하위 폴더가 자동 생성됩니다) ")
        backup_frame.pack(fill=tk.X, padx=5, pady=5)

        backup_entry = ttk.Entry(backup_frame, textvariable=self.backup_folder, width=70)
        backup_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        backup_button = ttk.Button(backup_frame, text="찾아보기", command=self.select_backup_folder)
        backup_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # 3. 시작 버튼 프레임 (3개의 버튼을 가로로 나열)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=(10, 0))
        button_frame.columnconfigure((0, 1, 2), weight=1) # 3개 버튼이 공간을 나눠가짐

        self.btn_photo = ttk.Button(button_frame, text="사진/동영상 백업 시작", command=lambda: self.start_backup_thread("MEDIA"))
        self.btn_photo.grid(row=0, column=0, padx=2, sticky="ew")

        self.btn_file = ttk.Button(button_frame, text="파일 백업 시작", command=lambda: self.start_backup_thread("FILE"))
        self.btn_file.grid(row=0, column=1, padx=2, sticky="ew")

        self.btn_link = ttk.Button(button_frame, text="링크 백업 시작", command=lambda: self.start_backup_thread("LINK"))
        self.btn_link.grid(row=0, column=2, padx=2, sticky="ew")
        
        # 4. 중지 버튼
        self.btn_stop = ttk.Button(main_frame, text="작업 중지", command=self.request_stop, state="disabled")
        self.btn_stop.pack(fill=tk.X, padx=5, pady=5)

        # 5. 로그 출력 창
        log_frame = ttk.LabelFrame(main_frame, text=" 진행 로그 ")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state='disabled')

    # --- GUI 공통 헬퍼 ---

    def log(self, message):
        """ 로그 창에 메시지를 스레드 안전하게 출력합니다. """
        print(message) # 콘솔에도 출력
        try:
            if self.root:
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, str(message) + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
                self.root.update_idletasks()
        except Exception as e:
            print(f"로그 업데이트 실패: {e}")

    def select_cookie_folder(self):
        folder = filedialog.askdirectory(initialdir=self.cookie_folder.get())
        if folder:
            self.cookie_folder.set(os.path.abspath(folder))
            self.log(f"쿠키 폴더가 설정되었습니다: {folder}")

    def select_backup_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.backup_folder.set(os.path.abspath(folder))
            self.log(f"메인 백업 폴더가 설정되었습니다: {folder}")
            
    def set_buttons_state(self, is_running):
        """ 백업 실행 상태에 따라 버튼 활성화/비활성화 """
        if is_running:
            self.btn_photo.config(state="disabled")
            self.btn_file.config(state="disabled")
            self.btn_link.config(state="disabled")
            self.btn_stop.config(state="normal")
        else:
            self.btn_photo.config(state="normal")
            self.btn_file.config(state="normal")
            self.btn_link.config(state="normal")
            self.btn_stop.config(state="disabled")
            
    def request_stop(self):
        """ 중지 버튼 클릭 시 플래그 설정 """
        self.log("...작업 중지를 요청했습니다. 현재 페이지 완료 후 중단됩니다...")
        self.stop_requested.set()
        self.btn_stop.config(state="disabled") # 중복 클릭 방지

    # --- 백업 공통 헬퍼 ---

    def sanitize_filename(self, filename):
        """ 파일명으로 사용할 수 없는 특수문자를 제거합니다. """
        if not filename:
            return ""
        return re.sub(r'[\\/*?:"<>|]', '_', filename).strip()
    
    def format_timestamp_file(self, ts_millis):
        """ 파일명용 날짜 형식: 'YYYY-MM-DD_HH-MM-SS' """
        if not ts_millis or ts_millis == 0:
            return "UnknownDate"
        try:
            dt_object = datetime.fromtimestamp(int(ts_millis) / 1000)
            return dt_object.strftime("%Y-%m-%d_%H-%M-%S")
        except Exception:
            return "InvalidDate"

    def format_timestamp_csv(self, ts_millis):
        """ CSV 내용용 날짜 형식: 'YYYY-MM-DD HH:MM:SS' """
        if not ts_millis or ts_millis == 0:
            return "UnknownDate"
        try:
            dt_object = datetime.fromtimestamp(int(ts_millis) / 1000)
            return dt_object.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "InvalidDate"

    def is_kakao_cookie(self, line):
        """ 쿠키 파일에서 유효한 카카오 도메인인지 확인 """
        return line.startswith('talkcloud.kakao.com') or line.startswith('.kakao.com') or line.startswith('drawer-api.kakao.com')

    def request_list(self, url):
        """ API에 목록을 요청 (공통) """
        try:
            response = requests.get(url, cookies=self.cookies, headers=self.REQ_HEADERS)
            response_content = response.content.decode('utf-8')
            return json.loads(response_content)
        except Exception as e:
            self.log(f'error on request get list {url}\n{e}')
            return None

    def request_download(self, url):
        """ API에 파일/사진 다운로드를 요청 (공통) """
        try:
            response = requests.get(f'{url}?attach', cookies=self.cookies, headers=self.REQ_HEADERS)
            return response.content
        except Exception as e:
            self.log(f'error on request get photo {url}\n{e}')
            return None

    def load_cookies(self):
        """ 쿠키 파일을 로드 (공통) """
        cookie_folder_path = self.cookie_folder.get()
        cookie_file_path = os.path.join(cookie_folder_path, 'talkcloud.kakao.com_cookies.txt')
        
        if not os.path.exists(cookie_file_path):
            self.log(f"오류: '{cookie_file_path}' 파일을 찾을 수 없습니다.")
            cookie_file_path_old = os.path.join(cookie_folder_path, 'drive.kakao.com_cookies.txt')
            if os.path.exists(cookie_file_path_old):
                self.log(f"경고: talkcloud...txt를 찾지 못해 '{cookie_file_path_old}'를 대신 사용합니다.")
                cookie_file_path = cookie_file_path_old
            else:
                self.log(f"'{cookie_file_path}' 또는 '{cookie_file_path_old}' 파일을 찾을 수 없습니다.")
                return False
        
        self.cookies = {}
        with open(cookie_file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            cookie_lines = [line for line in lines if self.is_kakao_cookie(line)]
            for cookie_line in cookie_lines:
                try:
                    parts = cookie_line.strip().split('\t')
                    if len(parts) >= 7:
                        self.cookies[parts[5].replace(' ', '')] = parts[6].replace('\n', '')
                except Exception as e:
                    self.log(f"쿠키 라인 처리 중 오류: {e}")

        if not self.cookies:
            self.log("오류: 쿠키 파일에서 유효한 카카오 쿠키를 찾지 못했습니다.")
            return False
            
        self.log("쿠키 로드 성공.")
        return True

    def get_last_downloaded_id(self, backup_path, log_suffix, check_zip):
        """ 이어받기를 위해 마지막 ID를 찾는 공통 함수 """
        self.log(f"'{log_suffix}' 로그를 기준으로 이전 백업 기록을 확인합니다...")
        latest_timestamp = 0
        latest_id_str = None
        
        json_files = glob.glob(f"{backup_path}/*{log_suffix}")
        if not json_files:
            self.log("이전 백업 기록이 없습니다.")
            return None

        for json_file_path in json_files:
            try:
                base_path, _ = json_file_path.rsplit(log_suffix, 1)
                
                # 사진/파일 백업의 경우, .zip 파일이 있어야 '성공'으로 간주
                if check_zip:
                    zip_file_path = f'{base_path}_photo.zip'
                    if not os.path.exists(zip_file_path):
                        self.log(f"경고: {json_file_path} 파일은 있으나, 짝이 되는 .zip 파일이 없어 건너뜁니다.")
                        continue # .zip이 없으면 건너뜀

                timestamp_str = os.path.basename(base_path)
                current_timestamp = int(timestamp_str)
                    
                if current_timestamp > latest_timestamp:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        items = data.get('items')
                        if items:
                            latest_timestamp = current_timestamp
                            latest_id_str = items[-1]['drawerId'] # 공통: drawerId
            except Exception as e:
                self.log(f"경고: {json_file_path} 파일 처리 중 오류 발생: {e}")
        
        if latest_id_str is None:
            self.log("유효한 이전 백업 ID를 찾지 못했습니다.")
            return None
        
        self.log(f"가장 최근에 완료된 백업의 마지막 ID: {latest_id_str}")
        return latest_id_str

    # --- 백업 실행 (스레드에서 실행됨) ---

    def start_backup_thread(self, backup_type):
        """ 백업 유형에 맞는 스레드를 시작하는 공통 함수 """
        
        main_backup_path = self.backup_folder.get()
        if not main_backup_path:
            self.log("오류: 메인 백업 저장 경로를 지정해주세요.")
            return
            
        if not self.load_cookies(): # 쿠키 로드 먼저 시도
            return
            
        self.stop_requested.clear() # 중지 플래그 초기화
        self.set_buttons_state(is_running=True) # 버튼 비활성화
        
        config = self.API_CONFIG[backup_type]
        
        # 1. 하위 폴더 경로 생성
        sub_folder_path = os.path.join(main_backup_path, config["folder_name"])
        try:
            os.makedirs(sub_folder_path, exist_ok=True) # 폴더가 없으면 생성
        except Exception as e:
            self.log(f"백업 폴더 생성 실패: {e}")
            self.set_buttons_state(is_running=False)
            return

        # 2. 백업 유형에 맞는 함수를 스레드로 실행
        if backup_type == "MEDIA" or backup_type == "FILE":
            target_function = self.run_media_file_backup
        elif backup_type == "LINK":
            target_function = self.run_link_backup
        else:
            self.log("오류: 알 수 없는 백업 유형입니다.")
            self.set_buttons_state(is_running=False)
            return

        # 3. 스레드 래퍼(Wrapper)를 사용하여 실행 (finally에서 버튼 복구)
        thread = threading.Thread(
            target=self.run_backup_wrapper, 
            args=(target_function, config, sub_folder_path), 
            daemon=True
        )
        thread.start()

    def run_backup_wrapper(self, target_function, config, sub_folder_path):
        """ 모든 백업 스레드를 감싸고, 종료 시 버튼을 복구하는 래퍼 """
        try:
            target_function(config, sub_folder_path)
        except Exception as e:
            self.log(f"치명적인 오류 발생: {e}")
        finally:
            self.log(f"{config['folder_name']} 작업이 종료되었습니다.")
            self.set_buttons_state(is_running=False) # 버튼 다시 활성화

    # --- 1. 사진 / 파일 백업 로직 ---
            
    def run_media_file_backup(self, api_config, backup_path):
        """ 사진(MEDIA)과 파일(FILE) 백업을 처리하는 메인 루프 """
        
        base_url = api_config["base_url"]
        log_suffix = api_config["log_suffix"]
        
        resume_id = self.get_last_downloaded_id(backup_path, log_suffix, check_zip=True)
        
        if resume_id:
            next_url = f'{base_url}&offset={resume_id}'
        else:
            self.log("새로운 백업을 시작합니다.")
            next_url = base_url
            
        page_count = 1

        while next_url:
            if self.stop_requested.is_set():
                self.log("작업 중단됨.")
                break
                
            self.log(f"--- 페이지 {page_count} 백업 시작 ---")
            
            file_list_json = self.request_list(next_url)

            if file_list_json is None:
                self.log("API 요청 중 오류가 발생하여 중단합니다.")
                break
                
            items = file_list_json.get('items')
            if not items:
                self.log('더 이상 백업할 항목이 없습니다.')
                break

            timestamp = int(time.time())
            download_path = f'{backup_path}/{timestamp}'
            os.makedirs(download_path)

            with open(f'{backup_path}/{timestamp}{log_suffix}', 'w') as file:
                json.dump(file_list_json, file)

            PHOTO_COUNT = len(items)
            download_success_flag = [True]
            threads = []

            items_per_thread = (PHOTO_COUNT + self.THREADS_COUNT - 1) // self.THREADS_COUNT
            photo_item_list_list = []
            for i in range(0, PHOTO_COUNT, items_per_thread):
                photo_item_list_list.append(items[i:i + items_per_thread])

            for photo_list_chunk in photo_item_list_list:
                thread = threading.Thread(target=self._worker_download, args=(photo_list_chunk, download_success_flag, download_path))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            download_success = download_success_flag[0]

            if download_success:
                try:
                    shutil.make_archive(f'{download_path}_photo', 'zip', download_path)
                    self.log(f'{download_path}_photo.zip 파일로 압축 완료')
                    
                    shutil.rmtree(download_path)
                    self.log('임시 폴더 삭제 완료.')
                    
                    last_id = items[-1]['drawerId']
                    next_url = f'{base_url}&offset={last_id}'
                    page_count += 1
                    time.sleep(1) 

                except Exception as e:
                    self.log(f"압축 또는 폴더 삭제 중 오류 발생: {e}")
                    next_url = None
            else:
                self.log("다운로드 중 오류가 발생했습니다. 프로그램을 중단합니다.")
                self.log(f"오류가 발생한 임시 폴더: {download_path} (수동으로 확인 및 삭제 필요)")
                next_url = None

    def _worker_download(self, photo_item_list, success_flag, download_path):
        """ (사진/파일 공통) 멀티스레드 다운로드 작업자 """
        for photo_item in photo_item_list:
            if not success_flag[0] or self.stop_requested.is_set():
                break
                
            photo_data = self.request_download(photo_item['url'])
            
            if photo_data:
                try:
                    date_str = self.format_timestamp_file(photo_item.get('createdAt'))
                    chat_name = self.sanitize_filename(photo_item.get('chatName') or 'NoChatroom')
                    
                    default_name = f"file_{photo_item.get('drawerId', photo_item['id'])}"
                    original_name_raw = photo_item.get('name') or default_name
                    
                    original_name_base, original_ext = os.path.splitext(original_name_raw)
                    original_name_sanitized = self.sanitize_filename(original_name_base)
                    
                    url_filename = photo_item['url'].split('/')[-1]
                    _, url_ext = os.path.splitext(url_filename)
                    
                    final_extension = url_ext if url_ext else (original_ext if original_ext else '.jpg')
                    
                    final_filename = f"{date_str}_{chat_name}_{original_name_sanitized}{final_extension}"
                    filepath = os.path.join(download_path, final_filename)
                    
                    counter = 1
                    base_filepath = filepath
                    while os.path.exists(filepath):
                        base, ext = os.path.splitext(base_filepath)
                        filepath = f"{base}_{counter}{ext}"
                        counter += 1

                    with open(filepath, 'wb') as f:
                        f.write(photo_data)
                    
                    self.log(f"downloaded: {final_filename}")

                except Exception as e:
                    self.log(f"파일명 생성 또는 저장 오류 ({photo_item.get('id', 'UnknownID')}): {e}")
                    success_flag[0] = False
            else:
                self.log(f"사진/파일 다운로드 실패: {str(photo_item.get('id', 'UnknownID'))}")
                success_flag[0] = False

    # --- 2. 링크 백업 로직 ---
            
    def run_link_backup(self, api_config, backup_path):
        """ 링크(LINK) 백업을 처리하는 메인 루프 """
        base_url = api_config["base_url"]
        log_suffix = api_config["log_suffix"]
        
        all_links = []
        
        # 링크는 이어받기 시, 중복 수집 후 마지막에 제거하므로
        # 기존 로그를 읽어 시작점을 찾습니다.
        resume_id = self.get_last_downloaded_id(backup_path, log_suffix, check_zip=False)
        
        if resume_id:
            next_url = f'{base_url}&offset={resume_id}'
        else:
            self.log("새로운 링크 백업을 시작합니다.")
            next_url = base_url
            
        page_count = 1

        while next_url:
            if self.stop_requested.is_set():
                self.log("작업 중단됨.")
                break
                
            self.log(f"--- 링크 페이지 {page_count} 수집 중 ---")
            
            file_list_json = self.request_list(next_url)

            if file_list_json is None:
                self.log("API 요청 중 오류가 발생하여 중단합니다.")
                break
                
            items = file_list_json.get('items')
            if not items:
                self.log('더 이상 백업할 링크가 없습니다.')
                break

            # 이어받기를 위해 매번 json 로그 저장
            try:
                timestamp = int(time.time())
                log_path = os.path.join(backup_path, f"{timestamp}{log_suffix}")
                with open(log_path, 'w', encoding='utf-8') as f:
                    json.dump(file_list_json, f)
            except Exception as e:
                self.log(f"경고: 링크 로그 파일 저장 실패: {e}")

            all_links.extend(items)
            self.log(f"수집된 총 링크: {len(all_links)}개")

            try:
                last_id = items[-1]['drawerId'] 
                next_url = f'{base_url}&offset={last_id}'
            except KeyError:
                self.log("오류: 'drawerId'를 찾을 수 없어 페이징이 불가능합니다.")
                next_url = None # 루프 중단
            except Exception as e:
                self.log(f"페이징 중 알 수 없는 오류: {e}")
                next_url = None # 루프 중단

            page_count += 1
            time.sleep(1)
        
        if all_links:
            # 이어받기 시 중복 데이터가 수집될 수 있으므로, 고유 ID(16진수) 기준으로 중복 제거
            unique_links = []
            seen_ids = set()
            # DESC(최신순)으로 수집했으므로, 순서대로 중복 제거
            for link in all_links: 
                link_id = link.get('id') 
                if link_id not in seen_ids:
                    unique_links.append(link)
                    seen_ids.add(link_id)
            
            self.log(f"총 {len(all_links)}개 수집, 중복 제거 후 {len(unique_links)}개")
            self.write_csv_backup(backup_path, unique_links)
        else:
            self.log("수집된 링크가 없습니다.")

    def write_csv_backup(self, backup_path, all_links):
        """ (링크 전용) 수집된 링크를 CSV 파일로 저장 """
        filepath = os.path.join(backup_path, "talkcloud_links_backup.csv")
        self.log(f"총 {len(all_links)}개의 링크를 CSV 파일로 저장합니다...")
        
        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Title", "URL"]) # 헤더
                
                for link in all_links:
                    date_str = self.format_timestamp_csv(link.get('createdAt'))
                    title_raw = link.get('title', '제목 없음')
                    title = " ".join(title_raw.split()) if title_raw else '제목 없음'
                    url_raw = link.get('url', '#')
                    url = " ".join(url_raw.split()) if url_raw else '#'
                    
                    writer.writerow([date_str, title, url])
                        
            self.log(f"성공: '{filepath}' 파일에 모든 링크를 저장했습니다.")
        except PermissionError:
            self.log(f"오류: '{filepath}' 파일을 쓸 수 없습니다. 파일이 다른 프로그램에서 열려있는지 확인하세요.")
        except Exception as e:
            self.log(f"CSV 파일 저장 중 치명적인 오류 발생: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TalkDriveUnifiedBackupApp(root)
    root.mainloop()

