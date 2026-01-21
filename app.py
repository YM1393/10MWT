# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import threading
from datetime import datetime
import csv
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib
matplotlib.use('TkAgg')
matplotlib.rcParams['font.family'] = 'Malgun Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# Supabase 연결
from supabase import create_client

SUPABASE_URL = "https://eaerehptwacqnuntmjgk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVhZXJlaHB0d2FjcW51bnRtamdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg5Mjk1NzQsImV4cCI6MjA4NDUwNTU3NH0.Mcgs4Xy_3h2eHxZAJtX7Si9UQAbjWxZhqO1M0E9A6uk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("10m 보행 테스트")
        self.root.geometry("1500x750")
        self.root.resizable(True, True)
        self.root.configure(bg='#1a1a2e')

        # 전체화면 상태
        self.is_fullscreen = False
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', self.exit_fullscreen)

        self.video_path = None
        self.cap = None
        self.model = None
        self.fps = 30
        self.is_analyzing = False
        self.current_frame = None  # 현재 표시 중인 프레임 저장

        # 사람 키 (cm)
        self.human_height_cm = 177

        # 측정
        self.total_distance_cm = 0
        self.frame_count = 0
        self.start_frame = None
        self.result_time = 0
        self.result_speed = 0
        self.measurement_started = False
        self.measurement_done = False

        # 사람 추적
        self.prev_foot_y = None
        self.prev_height_px = None
        self.first_person_box = None
        self.tracking_initialized = False

        # 카메라 거리 추정
        self.initial_distance_cm = 300
        self.reference_height_cm = 177  # 기준 키 (보정용)

        # 결과 리스트
        self.results_list = []

        # 측정별 발목 데이터 저장 {item_id: {'time': [], 'left_y': [], 'right_y': [], 'distance': []}}
        self.ankle_data_per_measurement = {}

        # 인라인 그래프
        self.inline_fig = None
        self.inline_canvas = None
        self.inline_ax = None
        self.graph_frame = None

        # 환자 관리 (Supabase)
        self.patients = []  # 환자 목록 캐시
        self.selected_patient_id = None  # 현재 선택된 환자 ID
        self.searched_patient_id = None  # 검색된 환자 ID (측정기록 필터용)
        self.searched_patient_name = None  # 검색된 환자 이름

        self.setup_styles()
        self.create_ui()
        self.load_patients()  # 환자 목록 로드

    def toggle_fullscreen(self, event=None):
        """전체화면 토글 (F11)"""
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes('-fullscreen', self.is_fullscreen)
        if hasattr(self, 'btn_fullscreen'):
            self.btn_fullscreen.config(text="창모드" if self.is_fullscreen else "전체화면")
        return "break"

    def exit_fullscreen(self, event=None):
        """전체화면 종료 (ESC)"""
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.root.attributes('-fullscreen', False)
            if hasattr(self, 'btn_fullscreen'):
                self.btn_fullscreen.config(text="전체화면")
        return "break"

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        # 프로그레스바 스타일
        style.configure("Rounded.Horizontal.TProgressbar",
                       troughcolor='#16213e',
                       background='#4ecca3',
                       darkcolor='#4ecca3',
                       lightcolor='#4ecca3',
                       bordercolor='#16213e',
                       thickness=12)

        # Treeview 스타일
        style.configure("Custom.Treeview",
                       background='#1f2940',
                       foreground='white',
                       fieldbackground='#1f2940',
                       rowheight=28,
                       font=('맑은 고딕', 9))
        style.configure("Custom.Treeview.Heading",
                       background='#16213e',
                       foreground='#4ecca3',
                       font=('맑은 고딕', 9, 'bold'))
        style.map("Custom.Treeview",
                 background=[('selected', '#4ecca3')],
                 foreground=[('selected', '#1a1a2e')])

    def create_rounded_frame(self, parent, bg_color):
        frame = tk.Frame(parent, bg=bg_color, highlightbackground=bg_color,
                        highlightthickness=2)
        return frame

    def on_resize(self, event=None):
        """창 크기 변경 시 레이아웃 조정"""
        if event and event.widget != self.root:
            return

        w = self.root.winfo_width()
        h = self.root.winfo_height()

        if w < 100 or h < 100:
            return

        padding = 15
        center_width = 300
        right_width = 290

        # 비디오 영역 너비 계산 (전체 - 중앙 - 오른쪽 - 패딩)
        left_width = w - center_width - right_width - padding * 4

        # 최소 크기 보장
        left_width = max(left_width, 400)

        card_height = h - padding * 2

        # 왼쪽 카드 (비디오)
        self.left_card.place(x=padding, y=padding, width=left_width, height=card_height)

        # 비디오 컨테이너
        video_height = card_height - 60
        self.video_container.place(x=10, y=10, width=left_width - 20, height=video_height)
        self.video_label.place(x=0, y=0, width=left_width - 20, height=video_height)

        # 프로그레스바
        self.progress_frame.place(x=10, y=card_height - 40, width=left_width - 20, height=30)
        self.progress.configure(length=left_width - 20)

        # 비디오 표시 크기 저장
        self.video_display_width = left_width - 20
        self.video_display_height = video_height

        # 중앙 카드
        center_x = padding + left_width + padding
        self.center_card.place(x=center_x, y=padding, width=center_width, height=card_height)

        # 오른쪽 카드
        right_x = center_x + center_width + padding
        self.right_card.place(x=right_x, y=padding, width=right_width, height=card_height)

        # 현재 프레임이 있으면 새 크기로 다시 표시
        if hasattr(self, 'current_frame') and self.current_frame is not None:
            self.redraw_current_frame()

    def redraw_current_frame(self):
        """현재 프레임을 새 크기로 다시 그리기"""
        if self.current_frame is None:
            return

        frame = self.current_frame
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame_rgb.shape[:2]

        label_w = self.video_display_width
        label_h = self.video_display_height

        scale = min(label_w/w, label_h/h)
        new_w, new_h = int(w*scale), int(h*scale)

        frame_resized = cv2.resize(frame_rgb, (new_w, new_h))
        img = ImageTk.PhotoImage(Image.fromarray(frame_resized))
        self.video_label.imgtk = img
        self.video_label.config(image=img, text='')

    def create_ui(self):
        # 비디오 표시 크기 (기본값)
        self.video_display_width = 840
        self.video_display_height = 620

        # 왼쪽 - 비디오 영역
        self.left_card = self.create_rounded_frame(self.root, '#16213e')

        self.video_container = tk.Frame(self.left_card, bg='#0f0f1a')

        self.video_label = tk.Label(self.video_container, bg='#0f0f1a',
                                   text="동영상을 업로드하세요",
                                   fg='#4ecca3', font=('맑은 고딕', 16, 'bold'))

        self.progress_frame = tk.Frame(self.left_card, bg='#16213e')

        self.progress = ttk.Progressbar(self.progress_frame, maximum=100, length=840,
                                       style="Rounded.Horizontal.TProgressbar")
        self.progress.pack(pady=8)

        # 중앙 - 컨트롤 패널
        self.center_card = self.create_rounded_frame(self.root, '#16213e')

        # 타이틀
        title_frame = tk.Frame(self.center_card, bg='#16213e')
        title_frame.pack(fill='x', pady=(15, 10))

        tk.Label(title_frame, text="10m 보행 테스트",
                font=('맑은 고딕', 16, 'bold'),
                bg='#16213e', fg='#ffffff').pack()

        # 전체화면 버튼
        self.btn_fullscreen = tk.Button(title_frame, text="전체화면 (F11)",
                                        command=self.toggle_fullscreen,
                                        font=('맑은 고딕', 9),
                                        bg='#2d3a4f', fg='white',
                                        activebackground='#4ecca3',
                                        relief='flat',
                                        cursor='hand2')
        self.btn_fullscreen.pack(pady=(5, 0))

        # 피험자 정보 입력 카드
        info_card = tk.Frame(self.center_card, bg='#1f2940')
        info_card.pack(fill='x', padx=15, pady=10)

        tk.Label(info_card, text="피험자 정보",
                bg='#1f2940', fg='#f1c40f',
                font=('맑은 고딕', 11, 'bold')).pack(pady=(10, 8))

        # 환자 선택 콤보박스
        patient_select_frame = tk.Frame(info_card, bg='#1f2940')
        patient_select_frame.pack(fill='x', padx=15, pady=(0, 8))

        tk.Label(patient_select_frame, text="환자",
                bg='#1f2940', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=6, anchor='w').pack(side='left')

        self.patient_combo = ttk.Combobox(patient_select_frame, font=('맑은 고딕', 10),
                                          width=18, state='readonly')
        self.patient_combo['values'] = ["-- 새 환자 --"]
        self.patient_combo.current(0)
        self.patient_combo.pack(side='left', padx=(5, 0))
        self.patient_combo.bind('<<ComboboxSelected>>', self.on_patient_select)

        # 환자 관리 버튼 프레임
        patient_btn_frame = tk.Frame(info_card, bg='#1f2940')
        patient_btn_frame.pack(fill='x', padx=15, pady=(0, 5))

        self.btn_add_patient = tk.Button(patient_btn_frame, text="환자추가",
                                         command=self.show_add_patient_dialog,
                                         font=('맑은 고딕', 8),
                                         bg='#27ae60', fg='white',
                                         relief='flat', cursor='hand2',
                                         width=7)
        self.btn_add_patient.pack(side='left', padx=(60, 3))

        self.btn_history = tk.Button(patient_btn_frame, text="히스토리",
                                     command=self.show_patient_history,
                                     font=('맑은 고딕', 8),
                                     bg='#3498db', fg='white',
                                     relief='flat', cursor='hand2',
                                     state='disabled', width=7)
        self.btn_history.pack(side='left', padx=3)

        self.btn_delete_patient = tk.Button(patient_btn_frame, text="삭제",
                                            command=self.delete_patient_from_db,
                                            font=('맑은 고딕', 8),
                                            bg='#e74c3c', fg='white',
                                            relief='flat', cursor='hand2',
                                            state='disabled', width=5)
        self.btn_delete_patient.pack(side='left', padx=3)

        # 이름 입력
        name_frame = tk.Frame(info_card, bg='#1f2940')
        name_frame.pack(fill='x', padx=15, pady=5)

        tk.Label(name_frame, text="이름",
                bg='#1f2940', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=6, anchor='w').pack(side='left')

        self.entry_name = tk.Entry(name_frame, font=('맑은 고딕', 11),
                                  bg='#2d3a4f', fg='white',
                                  insertbackground='white',
                                  relief='flat', width=15)
        self.entry_name.pack(side='left', padx=(5, 0), ipady=5)

        # 키 입력
        height_frame = tk.Frame(info_card, bg='#1f2940')
        height_frame.pack(fill='x', padx=15, pady=5)

        tk.Label(height_frame, text="키(cm)",
                bg='#1f2940', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=6, anchor='w').pack(side='left')

        self.entry_height = tk.Entry(height_frame, font=('맑은 고딕', 11),
                                    bg='#2d3a4f', fg='white',
                                    insertbackground='white',
                                    relief='flat', width=8)
        self.entry_height.pack(side='left', padx=(5, 0), ipady=5)
        self.entry_height.insert(0, "177")

        tk.Label(height_frame, text="cm",
                bg='#1f2940', fg='#7f8c8d',
                font=('맑은 고딕', 10)).pack(side='left', padx=(5, 0))

        # 성별 선택
        gender_frame = tk.Frame(info_card, bg='#1f2940')
        gender_frame.pack(fill='x', padx=15, pady=(5, 15))

        tk.Label(gender_frame, text="성별",
                bg='#1f2940', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=6, anchor='w').pack(side='left')

        self.gender_var = tk.StringVar(value="남")

        tk.Radiobutton(gender_frame, text="남",
                      variable=self.gender_var, value="남",
                      bg='#1f2940', fg='white', selectcolor='#2d3a4f',
                      activebackground='#1f2940', activeforeground='white',
                      font=('맑은 고딕', 10)).pack(side='left', padx=(5, 10))

        tk.Radiobutton(gender_frame, text="여",
                      variable=self.gender_var, value="여",
                      bg='#1f2940', fg='white', selectcolor='#2d3a4f',
                      activebackground='#1f2940', activeforeground='white',
                      font=('맑은 고딕', 10)).pack(side='left')

        # 업로드 버튼
        btn_frame = tk.Frame(self.center_card, bg='#16213e')
        btn_frame.pack(fill='x', pady=10, padx=20)

        self.btn_upload = tk.Button(btn_frame, text="동영상 업로드",
                                   command=self.upload_video,
                                   font=('맑은 고딕', 12, 'bold'),
                                   bg='#e94560', fg='white',
                                   activebackground='#ff6b6b',
                                   activeforeground='white',
                                   relief='flat',
                                   cursor='hand2',
                                   width=18, height=2)
        self.btn_upload.pack()

        self.lbl_file = tk.Label(self.center_card, text="선택된 파일 없음",
                                bg='#16213e', fg='#7f8c8d',
                                font=('맑은 고딕', 9),
                                wraplength=260)
        self.lbl_file.pack(pady=(5, 5))

        # 상태 표시
        status_card = tk.Frame(self.center_card, bg='#1f2940')
        status_card.pack(fill='x', padx=15, pady=5)

        self.lbl_status = tk.Label(status_card, text="대기중",
                                  bg='#1f2940', fg='#f39c12',
                                  font=('맑은 고딕', 11, 'bold'),
                                  pady=8)
        self.lbl_status.pack()

        # 실시간 거리
        distance_card = tk.Frame(self.center_card, bg='#2d3a4f')
        distance_card.pack(fill='x', padx=15, pady=8)

        tk.Label(distance_card, text="이동 거리",
                bg='#2d3a4f', fg='#bdc3c7',
                font=('맑은 고딕', 10)).pack(pady=(8, 0))

        self.lbl_distance = tk.Label(distance_card, text="0.00 m",
                                    bg='#2d3a4f', fg='#4ecca3',
                                    font=('맑은 고딕', 22, 'bold'))
        self.lbl_distance.pack(pady=(0, 8))

        # 결과 표시 카드
        result_card = tk.Frame(self.center_card, bg='#1f2940')
        result_card.pack(fill='x', padx=15, pady=8)

        tk.Label(result_card, text="측정 결과",
                bg='#1f2940', fg='#f1c40f',
                font=('맑은 고딕', 11, 'bold')).pack(pady=(10, 8))

        # 시간
        self.lbl_time = tk.Label(result_card, text="-- 초",
                                bg='#1f2940', fg='white',
                                font=('맑은 고딕', 26, 'bold'))
        self.lbl_time.pack()

        # 속도
        speed_frame = tk.Frame(result_card, bg='#1f2940')
        speed_frame.pack(pady=5)

        self.lbl_speed = tk.Label(speed_frame, text="-- m/s",
                                 bg='#1f2940', fg='#ecf0f1',
                                 font=('맑은 고딕', 14))
        self.lbl_speed.pack()

        self.lbl_speed_kmh = tk.Label(speed_frame, text="-- km/h",
                                     bg='#1f2940', fg='#7f8c8d',
                                     font=('맑은 고딕', 11))
        self.lbl_speed_kmh.pack()

        # 평가
        self.lbl_grade = tk.Label(result_card, text="",
                                 bg='#1f2940', fg='#2ecc71',
                                 font=('맑은 고딕', 13, 'bold'))
        self.lbl_grade.pack(pady=(5, 15))

        # 오른쪽 - 결과 리스트
        self.right_card = self.create_rounded_frame(self.root, '#16213e')

        tk.Label(self.right_card, text="측정 기록",
                font=('맑은 고딕', 14, 'bold'),
                bg='#16213e', fg='#ffffff').pack(pady=(15, 5))

        # 환자 검색 프레임
        search_frame = tk.Frame(self.right_card, bg='#16213e')
        search_frame.pack(fill='x', padx=10, pady=(0, 8))

        tk.Label(search_frame, text="환자검색:",
                bg='#16213e', fg='#bdc3c7',
                font=('맑은 고딕', 9)).pack(side='left')

        self.search_entry = tk.Entry(search_frame, font=('맑은 고딕', 10),
                                     bg='#2d3a4f', fg='white',
                                     insertbackground='white',
                                     relief='flat', width=12)
        self.search_entry.pack(side='left', padx=(5, 3), ipady=3)
        self.search_entry.bind('<Return>', lambda e: self.search_patient_records())

        self.btn_search = tk.Button(search_frame, text="검색",
                                    command=self.search_patient_records,
                                    font=('맑은 고딕', 8),
                                    bg='#9b59b6', fg='white',
                                    relief='flat', cursor='hand2',
                                    width=5)
        self.btn_search.pack(side='left', padx=2)

        self.btn_show_all = tk.Button(search_frame, text="전체",
                                      command=self.show_all_records,
                                      font=('맑은 고딕', 8),
                                      bg='#7f8c8d', fg='white',
                                      relief='flat', cursor='hand2',
                                      width=5)
        self.btn_show_all.pack(side='left', padx=2)

        # 현재 검색된 환자 표시
        self.search_status_label = tk.Label(self.right_card, text="",
                                            bg='#16213e', fg='#f1c40f',
                                            font=('맑은 고딕', 9))
        self.search_status_label.pack()

        # Treeview 컨테이너 (상단 절반)
        tree_frame = tk.Frame(self.right_card, bg='#1f2940')
        tree_frame.pack(fill='x', padx=10, pady=(0, 5))

        # Treeview (높이 줄임)
        columns = ('name', 'gender', 'height', 'time', 'speed', 'grade')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                style="Custom.Treeview", height=8)

        self.tree.heading('name', text='이름')
        self.tree.heading('gender', text='성별')
        self.tree.heading('height', text='키')
        self.tree.heading('time', text='시간')
        self.tree.heading('speed', text='속도')
        self.tree.heading('grade', text='평가')

        self.tree.column('name', width=50, anchor='center')
        self.tree.column('gender', width=35, anchor='center')
        self.tree.column('height', width=40, anchor='center')
        self.tree.column('time', width=50, anchor='center')
        self.tree.column('speed', width=45, anchor='center')
        self.tree.column('grade', width=45, anchor='center')

        # 스크롤바
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Treeview 클릭 이벤트 바인딩
        self.tree.bind('<<TreeviewSelect>>', self.on_record_select)

        # 버튼 프레임
        btn_list_frame = tk.Frame(self.right_card, bg='#16213e')
        btn_list_frame.pack(pady=(5, 5))

        # 저장 버튼
        self.btn_save = tk.Button(btn_list_frame, text="CSV 저장",
                                 command=self.save_results,
                                 font=('맑은 고딕', 9),
                                 bg='#3498db', fg='white',
                                 activebackground='#2980b9',
                                 relief='flat',
                                 cursor='hand2',
                                 width=8)
        self.btn_save.pack(side='left', padx=3)

        # 삭제 버튼
        self.btn_delete = tk.Button(btn_list_frame, text="선택 삭제",
                                   command=self.delete_selected,
                                   font=('맑은 고딕', 9),
                                   bg='#e74c3c', fg='white',
                                   activebackground='#c0392b',
                                   relief='flat',
                                   cursor='hand2',
                                   width=8)
        self.btn_delete.pack(side='left', padx=3)

        # 전체 그래프 버튼
        self.btn_graph = tk.Button(btn_list_frame, text="전체 그래프",
                                  command=self.show_graph,
                                  font=('맑은 고딕', 9),
                                  bg='#9b59b6', fg='white',
                                  activebackground='#8e44ad',
                                  relief='flat',
                                  cursor='hand2',
                                  width=8)
        self.btn_graph.pack(side='left', padx=3)

        # 하단 그래프 영역
        graph_label = tk.Label(self.right_card, text="기록을 클릭하면 그래프가 표시됩니다",
                              font=('맑은 고딕', 9),
                              bg='#16213e', fg='#7f8c8d')
        graph_label.pack(pady=(5, 2))

        self.graph_frame = tk.Frame(self.right_card, bg='#1f2940')
        self.graph_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        # 그래프 캔버스 초기화
        self.inline_fig = None
        self.inline_canvas = None
        self.init_inline_graph()

        # 리사이즈 이벤트 바인딩
        self.root.bind('<Configure>', self.on_resize)

        # 초기 레이아웃 설정
        self.root.update_idletasks()
        self.on_resize()

    def delete_selected(self):
        selected = self.tree.selection()
        if selected:
            for item in selected:
                # 발목 데이터도 삭제
                if item in self.ankle_data_per_measurement:
                    del self.ankle_data_per_measurement[item]
                self.tree.delete(item)
            # 삭제 후 그래프 초기화
            self.init_inline_graph()

    def init_inline_graph(self):
        """인라인 그래프 영역 초기화"""
        # 기존 캔버스 제거
        if self.inline_canvas:
            self.inline_canvas.get_tk_widget().destroy()
            plt.close(self.inline_fig)

        # 빈 그래프 생성
        self.inline_fig, self.inline_ax = plt.subplots(figsize=(2.8, 3.5))
        self.inline_fig.patch.set_facecolor('#1f2940')
        self.inline_ax.set_facecolor('#1f2940')
        self.inline_ax.text(0.5, 0.5, '기록을 선택하세요',
                           ha='center', va='center',
                           fontsize=10, color='#7f8c8d',
                           transform=self.inline_ax.transAxes)
        self.inline_ax.axis('off')

        plt.tight_layout()

        self.inline_canvas = FigureCanvasTkAgg(self.inline_fig, master=self.graph_frame)
        self.inline_canvas.draw()
        self.inline_canvas.get_tk_widget().pack(fill='both', expand=True)

    def on_record_select(self, event):
        """Treeview 항목 선택 시 그래프 표시"""
        selected = self.tree.selection()
        if not selected:
            return

        # 선택된 항목의 데이터 가져오기
        item = selected[0]
        values = self.tree.item(item)['values']

        name = str(values[0])
        gender = str(values[1])
        height = str(values[2])
        time_val = float(str(values[3]).replace('s', ''))
        speed_val = float(values[4])
        grade = str(values[5])

        # 기존 캔버스 제거
        if self.inline_canvas:
            self.inline_canvas.get_tk_widget().destroy()
            plt.close(self.inline_fig)

        # 새 그래프 생성 (1x2 가로 배치)
        self.inline_fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2.8, 3.2))
        self.inline_fig.patch.set_facecolor('#1f2940')

        # 평가에 따른 색상
        if grade == '정상':
            color = '#2ecc71'
        elif grade == '약간느림':
            color = '#f1c40f'
        elif grade == '느림':
            color = '#e67e22'
        else:
            color = '#e74c3c'

        # 제목
        self.inline_fig.suptitle(f'{name} ({gender}, {height}cm)', fontsize=10, fontweight='bold', color='white', y=0.98)

        # 시간 막대그래프 (왼쪽)
        bars1 = ax1.bar(['시간'], [time_val], color=color, width=0.5)
        ax1.axhline(y=10, color='#4ecca3', linestyle='--', linewidth=1.5)
        ax1.set_ylim(0, max(time_val * 1.3, 15))
        ax1.set_ylabel('초', fontsize=9, color='white')
        ax1.set_facecolor('#16213e')
        ax1.tick_params(colors='white', labelsize=8)
        ax1.spines['bottom'].set_color('white')
        ax1.spines['left'].set_color('white')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # 시간 값 표시 (막대 위)
        ax1.text(0, time_val + 0.5, f'{time_val:.2f}s', ha='center', fontsize=9, color='white', fontweight='bold')
        ax1.text(0.5, 10.5, '기준', ha='left', fontsize=7, color='#4ecca3')

        # 속도 막대그래프 (오른쪽)
        bars2 = ax2.bar(['속도'], [speed_val], color=color, width=0.5)
        ax2.axhline(y=1.0, color='#4ecca3', linestyle='--', linewidth=1.5)
        ax2.set_ylim(0, max(speed_val * 1.3, 1.5))
        ax2.set_ylabel('m/s', fontsize=9, color='white')
        ax2.set_facecolor('#16213e')
        ax2.tick_params(colors='white', labelsize=8)
        ax2.spines['bottom'].set_color('white')
        ax2.spines['left'].set_color('white')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

        # 속도 값 표시 (막대 위)
        ax2.text(0, speed_val + 0.05, f'{speed_val:.2f}', ha='center', fontsize=9, color='white', fontweight='bold')
        ax2.text(0.5, 1.05, '기준', ha='left', fontsize=7, color='#4ecca3')

        # 평가 표시
        self.inline_fig.text(0.5, 0.02, f'평가: {grade}', ha='center', fontsize=11,
                            fontweight='bold', color=color)

        plt.tight_layout(rect=[0, 0.06, 1, 0.93])

        self.inline_canvas = FigureCanvasTkAgg(self.inline_fig, master=self.graph_frame)
        self.inline_canvas.draw()
        self.inline_canvas.get_tk_widget().pack(fill='both', expand=True)

    def save_results(self):
        # Treeview에 데이터가 있는지 확인
        items = self.tree.get_children()
        if not items:
            messagebox.showwarning("경고", "저장할 데이터가 없습니다.")
            return

        # 저장 옵션 선택 다이얼로그
        self.show_save_dialog(items)

    def show_save_dialog(self, items):
        """CSV 저장 옵션 선택 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title("CSV 저장 옵션")
        dialog.geometry("420x480")
        dialog.configure(bg='#1a1a2e')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        # 중앙 정렬
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 480) // 2
        dialog.geometry(f"420x480+{x}+{y}")

        # 제목
        tk.Label(dialog, text="저장할 데이터를 선택하세요",
                font=('맑은 고딕', 14, 'bold'),
                bg='#1a1a2e', fg='white').pack(pady=(20, 10))

        # 검색된 환자 정보 표시
        if self.searched_patient_name:
            info_frame = tk.Frame(dialog, bg='#27ae60')
            info_frame.pack(fill='x', padx=20, pady=(0, 10))
            tk.Label(info_frame, text=f"📁 '{self.searched_patient_name}' 환자의 기록만 저장됩니다",
                    font=('맑은 고딕', 10, 'bold'),
                    bg='#27ae60', fg='white').pack(pady=8)

        # 옵션 1: 요약 데이터만
        self.save_option = tk.IntVar(value=1)

        frame1 = tk.Frame(dialog, bg='#16213e')
        frame1.pack(fill='x', padx=20, pady=5)

        tk.Radiobutton(frame1, text="측정 요약만 저장",
                      variable=self.save_option, value=1,
                      bg='#16213e', fg='white', selectcolor='#2d3a4f',
                      activebackground='#16213e', activeforeground='white',
                      font=('맑은 고딕', 11)).pack(anchor='w', padx=10, pady=10)

        tk.Label(frame1, text="  (이름, 키, 시간, 속도, 평가)",
                bg='#16213e', fg='#7f8c8d',
                font=('맑은 고딕', 9)).pack(anchor='w', padx=30)

        # 옵션 2: 발목 데이터 포함
        frame2 = tk.Frame(dialog, bg='#16213e')
        frame2.pack(fill='x', padx=20, pady=5)

        tk.Radiobutton(frame2, text="발목 좌표 데이터 포함 저장",
                      variable=self.save_option, value=2,
                      bg='#16213e', fg='white', selectcolor='#2d3a4f',
                      activebackground='#16213e', activeforeground='white',
                      font=('맑은 고딕', 11)).pack(anchor='w', padx=10, pady=10)

        tk.Label(frame2, text="  (시간, 왼발목Y, 오른발목Y, 누적거리)",
                bg='#16213e', fg='#7f8c8d',
                font=('맑은 고딕', 9)).pack(anchor='w', padx=30)

        # 발목 데이터가 있는 측정 수 표시
        ankle_count = len(self.ankle_data_per_measurement)
        tk.Label(frame2, text=f"  발목 데이터 보유: {ankle_count}명",
                bg='#16213e', fg='#4ecca3',
                font=('맑은 고딕', 9)).pack(anchor='w', padx=30, pady=(5, 0))

        # 개별 저장 옵션 (발목 데이터 각각)
        frame3 = tk.Frame(dialog, bg='#16213e')
        frame3.pack(fill='x', padx=20, pady=5)

        tk.Radiobutton(frame3, text="발목 데이터 개별 CSV 저장",
                      variable=self.save_option, value=3,
                      bg='#16213e', fg='white', selectcolor='#2d3a4f',
                      activebackground='#16213e', activeforeground='white',
                      font=('맑은 고딕', 11)).pack(anchor='w', padx=10, pady=10)

        tk.Label(frame3, text="  (각 측정별로 별도 파일 생성)",
                bg='#16213e', fg='#7f8c8d',
                font=('맑은 고딕', 9)).pack(anchor='w', padx=30)

        # 구분선
        tk.Frame(dialog, bg='#2d3a4f', height=2).pack(fill='x', padx=20, pady=(20, 10))

        # 버튼 프레임
        btn_frame = tk.Frame(dialog, bg='#1a1a2e')
        btn_frame.pack(pady=(10, 20))

        save_btn = tk.Button(btn_frame, text="저장",
                 command=lambda: self.execute_save(dialog, items),
                 font=('맑은 고딕', 12, 'bold'),
                 bg='#4ecca3', fg='#1a1a2e',
                 activebackground='#3db892',
                 relief='flat', cursor='hand2',
                 width=12, height=2)
        save_btn.pack(side='left', padx=15)

        cancel_btn = tk.Button(btn_frame, text="취소",
                 command=dialog.destroy,
                 font=('맑은 고딕', 12, 'bold'),
                 bg='#e74c3c', fg='white',
                 activebackground='#c0392b',
                 relief='flat', cursor='hand2',
                 width=12, height=2)
        cancel_btn.pack(side='left', padx=15)

    def execute_save(self, dialog, items):
        """선택한 옵션에 따라 저장 실행"""
        option = self.save_option.get()
        dialog.destroy()

        if option == 1:
            # 요약만 저장
            self.save_summary_only(items)
        elif option == 2:
            # 요약 + 발목 데이터 통합 저장
            self.save_with_ankle_data(items)
        elif option == 3:
            # 발목 데이터 개별 저장
            self.save_ankle_data_separately(items)

    def save_summary_only(self, items):
        """측정 요약만 저장"""
        # 파일명에 환자 이름 포함 (검색된 경우)
        if self.searched_patient_name:
            filename = f"10MWT_{self.searched_patient_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        else:
            filename = f"10MWT_요약_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        file_path = filedialog.asksaveasfilename(
            title="측정 요약 저장",
            defaultextension=".csv",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
            initialfile=filename
        )

        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['이름', '성별', '키(cm)', '시간(초)', '속도(m/s)', '평가'])
                    for item in items:
                        values = self.tree.item(item)['values']
                        writer.writerow(values)

                messagebox.showinfo("저장 완료", f"측정 요약이 저장되었습니다.\n{file_path}")
            except Exception as e:
                messagebox.showerror("에러", f"저장 실패\n{e}")

    def save_with_ankle_data(self, items):
        """요약 + 발목 데이터 통합 저장"""
        if self.searched_patient_name:
            filename = f"10MWT_{self.searched_patient_name}_전체_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        else:
            filename = f"10MWT_전체_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        file_path = filedialog.asksaveasfilename(
            title="전체 데이터 저장",
            defaultextension=".csv",
            filetypes=[("CSV 파일", "*.csv"), ("모든 파일", "*.*")],
            initialfile=filename
        )

        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)

                    # 측정 요약
                    writer.writerow(['=== 측정 요약 ==='])
                    writer.writerow(['이름', '성별', '키(cm)', '시간(초)', '속도(m/s)', '평가'])
                    for item in items:
                        values = self.tree.item(item)['values']
                        writer.writerow(values)

                    writer.writerow([])

                    # 각 측정별 발목 데이터
                    for item in items:
                        if item in self.ankle_data_per_measurement:
                            data = self.ankle_data_per_measurement[item]
                            gender = data.get('gender', '')
                            writer.writerow([])
                            writer.writerow([f"=== {data['name']} ({gender}, {data['height']}cm) 발목 좌표 ==="])
                            writer.writerow(['시간(초)', '왼발목_Y(px)', '오른발목_Y(px)', '누적거리(m)'])

                            for i in range(len(data['time'])):
                                writer.writerow([
                                    f"{data['time'][i]:.3f}",
                                    f"{data['left_y'][i]:.1f}" if data['left_y'][i] > 0 else "0",
                                    f"{data['right_y'][i]:.1f}" if data['right_y'][i] > 0 else "0",
                                    f"{data['distance'][i]:.4f}"
                                ])

                saved_count = sum(1 for item in items if item in self.ankle_data_per_measurement)
                messagebox.showinfo("저장 완료", f"전체 데이터가 저장되었습니다.\n{file_path}\n\n발목 데이터 포함: {saved_count}명")
            except Exception as e:
                messagebox.showerror("에러", f"저장 실패\n{e}")

    def save_ankle_data_separately(self, items):
        """발목 데이터를 각각 별도 파일로 저장"""
        # 폴더 선택
        folder_path = filedialog.askdirectory(title="발목 데이터 저장 폴더 선택")

        if folder_path:
            try:
                saved_count = 0
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                # 먼저 요약 파일 저장 (환자명 포함)
                if self.searched_patient_name:
                    summary_path = os.path.join(folder_path, f"10MWT_{self.searched_patient_name}_요약_{timestamp}.csv")
                else:
                    summary_path = os.path.join(folder_path, f"10MWT_요약_{timestamp}.csv")
                with open(summary_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['이름', '성별', '키(cm)', '시간(초)', '속도(m/s)', '평가'])
                    for item in items:
                        values = self.tree.item(item)['values']
                        writer.writerow(values)

                # 각 측정별 발목 데이터 파일 저장
                for item in items:
                    if item in self.ankle_data_per_measurement:
                        data = self.ankle_data_per_measurement[item]
                        name = data['name'].replace(' ', '_')
                        gender = data.get('gender', '')
                        file_name = f"발목데이터_{name}_{timestamp}.csv"
                        file_path = os.path.join(folder_path, file_name)

                        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                            writer = csv.writer(f)
                            writer.writerow([f"피험자: {data['name']}", f"성별: {gender}", f"키: {data['height']}cm"])
                            writer.writerow(['시간(초)', '왼발목_Y(px)', '오른발목_Y(px)', '누적거리(m)'])

                            for i in range(len(data['time'])):
                                writer.writerow([
                                    f"{data['time'][i]:.3f}",
                                    f"{data['left_y'][i]:.1f}" if data['left_y'][i] > 0 else "0",
                                    f"{data['right_y'][i]:.1f}" if data['right_y'][i] > 0 else "0",
                                    f"{data['distance'][i]:.4f}"
                                ])
                        saved_count += 1

                messagebox.showinfo("저장 완료",
                    f"파일이 저장되었습니다.\n\n"
                    f"저장 위치: {folder_path}\n"
                    f"요약 파일: 1개\n"
                    f"발목 데이터 파일: {saved_count}개")
            except Exception as e:
                messagebox.showerror("에러", f"저장 실패\n{e}")

    def upload_video(self):
        # 키 값 업데이트
        try:
            height = int(self.entry_height.get())
            if 100 <= height <= 250:
                self.human_height_cm = height
            else:
                messagebox.showwarning("경고", "키는 100~250cm 사이로 입력하세요.")
                return
        except ValueError:
            messagebox.showwarning("경고", "올바른 키 값을 입력하세요.")
            return

        # 이름 확인
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("경고", "이름을 입력하세요.")
            return

        path = filedialog.askopenfilename(
            title="동영상 파일 선택",
            filetypes=[("동영상", "*.mp4 *.avi *.mov *.mkv *.wmv"), ("모든 파일", "*.*")]
        )

        if path:
            self.video_path = path
            self.cap = cv2.VideoCapture(path)

            if self.cap.isOpened():
                self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30

                ret, frame = self.cap.read()
                if ret:
                    self.show_frame(frame)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

                fname = os.path.basename(path)
                self.lbl_file.config(text=f"{fname}", fg='#4ecca3')
                self.lbl_status.config(text="분석 시작...")

                self.root.after(500, self.start_analysis)

    def start_analysis(self):
        if not self.model:
            self.lbl_status.config(text="AI Pose 모델 로딩중 (고정밀)...")
            self.root.update()
            try:
                from ultralytics import YOLO
                # 더 정확한 모델 사용 (n < s < m < l < x)
                self.model = YOLO('yolov8m-pose.pt')
            except Exception as e:
                messagebox.showerror("에러", f"YOLO Pose 로드 실패\n{e}")
                return

        self.reset()
        self.is_analyzing = True
        self.btn_upload.config(state=tk.DISABLED)

        threading.Thread(target=self.analyze, daemon=True).start()

    def reset(self):
        self.total_distance_cm = 0
        self.frame_count = 0
        self.start_frame = None
        self.result_time = 0
        self.result_speed = 0
        self.measurement_started = False
        self.measurement_done = False
        self.prev_foot_y = None
        self.prev_height_px = None
        self.first_person_box = None
        self.tracking_initialized = False

        # 키포인트 추적용
        self.prev_keypoints = None
        self.prev_ankle_y = None

        # 스무딩 버퍼 (Moving Average)
        self.smoothing_window = 5  # 5프레임 평균
        self.height_buffer = []  # 픽셀 높이 버퍼
        self.ankle_y_buffer = []  # 발목 Y 버퍼

        # 이상치 제거 임계값
        self.outlier_threshold_height = 50  # 픽셀 높이 변화 임계값
        self.outlier_threshold_ankle = 30   # 발목 Y 변화 임계값

        # 발목 좌표 기록 (그래프용)
        self.ankle_history_time = []
        self.ankle_history_left_y = []
        self.ankle_history_right_y = []
        self.ankle_history_distance = []  # 누적 거리

        # UI 초기화
        self.lbl_time.config(text="-- 초")
        self.lbl_speed.config(text="-- m/s")
        self.lbl_speed_kmh.config(text="-- km/h")
        self.lbl_grade.config(text="")
        self.lbl_distance.config(text="0.00 m")
        self.progress.configure(value=0)

    def smooth_value(self, buffer, new_value, window_size):
        """Moving Average 스무딩"""
        buffer.append(new_value)
        if len(buffer) > window_size:
            buffer.pop(0)
        return sum(buffer) / len(buffer)

    def is_outlier(self, prev_value, new_value, threshold):
        """이상치 검출"""
        if prev_value is None:
            return False
        return abs(new_value - prev_value) > threshold

    def get_weighted_ankle_y(self, left_ankle, right_ankle):
        """신뢰도 가중 평균으로 발목 Y 계산"""
        left_y, left_conf = left_ankle[1], left_ankle[2]
        right_y, right_conf = right_ankle[1], right_ankle[2]

        # 둘 다 신뢰도 낮으면 None 반환
        if left_conf < 0.3 and right_conf < 0.3:
            return None

        # 신뢰도 가중 평균
        if left_conf > 0.3 and right_conf > 0.3:
            total_conf = left_conf + right_conf
            weighted_y = (left_y * left_conf + right_y * right_conf) / total_conf
            return weighted_y
        elif left_conf > 0.3:
            return left_y
        else:
            return right_y

    def is_valid_person(self, box, frame_h, frame_w, confidence):
        x1, y1, x2, y2 = box
        box_w = x2 - x1
        box_h = y2 - y1

        if confidence < 0.5:
            return False
        if box_w < 30 or box_h < 60:
            return False

        aspect_ratio = box_h / box_w if box_w > 0 else 0
        if aspect_ratio < 1.0 or aspect_ratio > 5.0:
            return False

        return True

    def calc_iou(self, box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2-x1) * max(0, y2-y1)
        area1 = (box1[2]-box1[0]) * (box1[3]-box1[1])
        area2 = (box2[2]-box2[0]) * (box2[3]-box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0

    def find_same_person(self, boxes, prev_box, frame_h, frame_w):
        best_box = None
        best_score = -1
        prev_cx = (prev_box[0] + prev_box[2]) // 2
        prev_cy = (prev_box[1] + prev_box[3]) // 2

        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
            conf = float(box.conf[0].cpu().numpy())
            curr_box = (x1, y1, x2, y2)

            if not self.is_valid_person(curr_box, frame_h, frame_w, conf):
                continue

            cx, cy = (x1+x2)//2, (y1+y2)//2

            iou = self.calc_iou(prev_box, curr_box)
            dist = np.sqrt((cx - prev_cx)**2 + (cy - prev_cy)**2)
            dist_score = 1 / (1 + dist/100)

            score = iou * 0.4 + dist_score * 0.4 + conf * 0.2

            if score > best_score:
                best_score = score
                best_box = curr_box

        return best_box if best_score >= 0.1 else None

    def draw_ankle_graph(self, frame, graph_height=150):
        """영상 하단에 발목 좌표 및 누적 거리 그래프 그리기"""
        h, w = frame.shape[:2]

        # 그래프 영역 배경 (반투명 검정)
        overlay = frame.copy()
        graph_top = h - graph_height - 10
        cv2.rectangle(overlay, (10, graph_top), (w - 10, h - 10), (20, 20, 30), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        # 그래프 테두리
        cv2.rectangle(frame, (10, graph_top), (w - 10, h - 10), (100, 100, 100), 1)

        if len(self.ankle_history_time) < 2:
            cv2.putText(frame, "Measuring...", (20, graph_top + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            return frame

        # 그래프 영역 좌표
        graph_left = 60
        graph_right = w - 70
        graph_bottom = h - 25
        graph_top_inner = graph_top + 35

        graph_width = graph_right - graph_left
        graph_height_inner = graph_bottom - graph_top_inner

        # 최근 300 프레임만 표시 (약 10초)
        max_points = 300
        times = self.ankle_history_time[-max_points:]
        left_ys = self.ankle_history_left_y[-max_points:]
        right_ys = self.ankle_history_right_y[-max_points:]
        distances = self.ankle_history_distance[-max_points:]

        if len(times) < 2:
            return frame

        # Y축 범위 계산 (발목)
        all_ys = [y for y in left_ys + right_ys if y > 0]
        if not all_ys:
            return frame

        min_y = min(all_ys) - 20
        max_y = max(all_ys) + 20
        y_range = max_y - min_y if max_y != min_y else 1

        # 거리 범위
        max_dist = max(distances) if distances else 10
        max_dist = max(max_dist, 0.1)

        # 시간 범위
        min_time = times[0]
        max_time = times[-1]
        time_range = max_time - min_time if max_time != min_time else 1

        # 왼발목 그래프 (파란색)
        left_points = []
        for i, (t, y) in enumerate(zip(times, left_ys)):
            if y > 0:
                px = int(graph_left + (t - min_time) / time_range * graph_width)
                py = int(graph_bottom - (y - min_y) / y_range * graph_height_inner)
                left_points.append((px, py))

        if len(left_points) > 1:
            for i in range(len(left_points) - 1):
                cv2.line(frame, left_points[i], left_points[i+1], (255, 150, 100), 2)

        # 오른발목 그래프 (주황색)
        right_points = []
        for i, (t, y) in enumerate(zip(times, right_ys)):
            if y > 0:
                px = int(graph_left + (t - min_time) / time_range * graph_width)
                py = int(graph_bottom - (y - min_y) / y_range * graph_height_inner)
                right_points.append((px, py))

        if len(right_points) > 1:
            for i in range(len(right_points) - 1):
                cv2.line(frame, right_points[i], right_points[i+1], (100, 150, 255), 2)

        # 누적 거리 그래프 (초록색)
        dist_points = []
        for t, d in zip(times, distances):
            px = int(graph_left + (t - min_time) / time_range * graph_width)
            py = int(graph_bottom - (d / max_dist) * graph_height_inner)
            dist_points.append((px, py))

        if len(dist_points) > 1:
            for i in range(len(dist_points) - 1):
                cv2.line(frame, dist_points[i], dist_points[i+1], (100, 255, 100), 2)

        # 라벨 및 범례
        cv2.putText(frame, "Ankle Y & Distance", (20, graph_top + 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 범례
        legend_x = graph_left + 150
        cv2.putText(frame, "L-Ankle", (legend_x, graph_top + 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 150, 100), 1)
        cv2.putText(frame, "R-Ankle", (legend_x + 70, graph_top + 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 150, 255), 1)
        cv2.putText(frame, "Distance", (legend_x + 140, graph_top + 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 255, 100), 1)

        # 현재 값 표시
        curr_left_y = left_ys[-1] if left_ys[-1] > 0 else 0
        curr_right_y = right_ys[-1] if right_ys[-1] > 0 else 0
        curr_dist = distances[-1] if distances else 0

        # Y축 라벨 (왼쪽)
        cv2.putText(frame, "Y(px)", (15, graph_top + 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        cv2.putText(frame, f"{int(max_y)}", (15, graph_top_inner + 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        cv2.putText(frame, f"{int(min_y)}", (15, graph_bottom),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

        # 거리 축 라벨 (오른쪽)
        cv2.putText(frame, "Dist", (w - 55, graph_top + 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 255, 100), 1)
        cv2.putText(frame, f"{max_dist:.1f}m", (w - 60, graph_top_inner + 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 255, 100), 1)
        cv2.putText(frame, "0m", (w - 45, graph_bottom),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 255, 100), 1)

        # 현재 시간 및 값 표시
        cv2.putText(frame, f"T:{times[-1]:.2f}s  L:{int(curr_left_y)}  R:{int(curr_right_y)}  D:{curr_dist:.2f}m",
                   (graph_left, h - 12),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        return frame

    def draw_skeleton(self, frame, keypoints):
        """키포인트 스켈레톤 그리기"""
        # COCO 스켈레톤 연결
        skeleton = [
            (0, 1), (0, 2), (1, 3), (2, 4),  # 얼굴
            (5, 6),  # 어깨
            (5, 7), (7, 9),  # 왼팔
            (6, 8), (8, 10),  # 오른팔
            (5, 11), (6, 12),  # 몸통
            (11, 12),  # 엉덩이
            (11, 13), (13, 15),  # 왼다리
            (12, 14), (14, 16)   # 오른다리
        ]

        # 관절 색상 (부위별)
        colors = {
            'face': (255, 200, 100),      # 연파랑
            'arm': (100, 255, 100),       # 연초록
            'body': (255, 255, 100),      # 연청록
            'leg': (100, 200, 255)        # 연주황
        }

        # 스켈레톤 선 그리기
        for i, (p1, p2) in enumerate(skeleton):
            if keypoints[p1][2] > 0.5 and keypoints[p2][2] > 0.5:
                pt1 = (int(keypoints[p1][0]), int(keypoints[p1][1]))
                pt2 = (int(keypoints[p2][0]), int(keypoints[p2][1]))

                if i < 4:
                    color = colors['face']
                elif i < 9:
                    color = colors['arm']
                elif i < 13:
                    color = colors['body']
                else:
                    color = colors['leg']

                cv2.line(frame, pt1, pt2, color, 2)

        # 관절점 그리기
        for i, kp in enumerate(keypoints):
            if kp[2] > 0.5:
                x, y = int(kp[0]), int(kp[1])
                # 발목은 더 크게 표시
                if i in [15, 16]:
                    cv2.circle(frame, (x, y), 8, (0, 0, 255), -1)
                else:
                    cv2.circle(frame, (x, y), 4, (0, 255, 255), -1)

    def analyze(self):
        self.cap = cv2.VideoCapture(self.video_path)
        total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        self.root.after(0, lambda: self.lbl_status.config(text="포즈 감지중..."))

        while self.is_analyzing and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break

            self.frame_count += 1
            h, w = frame.shape[:2]

            prog = (self.frame_count / total) * 100
            self.root.after(0, lambda p=prog: self.progress.configure(value=p))

            results = self.model(frame, conf=0.4, verbose=False)

            target_box = None
            target_keypoints = None

            for r in results:
                if r.keypoints is not None and len(r.boxes) > 0:
                    keypoints_data = r.keypoints.data.cpu().numpy()
                    boxes_data = r.boxes

                    if not self.tracking_initialized:
                        # 첫 프레임: 가장 큰 사람 선택
                        max_area = 0
                        for idx, box in enumerate(boxes_data):
                            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                            conf = float(box.conf[0].cpu().numpy())
                            curr_box = (x1, y1, x2, y2)

                            if not self.is_valid_person(curr_box, h, w, conf):
                                continue

                            area = (x2-x1) * (y2-y1)
                            if area > max_area:
                                max_area = area
                                target_box = curr_box
                                target_keypoints = keypoints_data[idx]

                        if target_box and target_keypoints is not None:
                            self.first_person_box = target_box
                            self.prev_keypoints = target_keypoints
                            self.tracking_initialized = True
                            self.measurement_started = True
                            self.start_frame = self.frame_count

                            x1, y1, x2, y2 = target_box
                            self.prev_height_px = y2 - y1

                            # 발목 위치로 초기화 (왼발목:15, 오른발목:16)
                            left_ankle = target_keypoints[15]
                            right_ankle = target_keypoints[16]
                            if left_ankle[2] > 0.5 and right_ankle[2] > 0.5:
                                self.prev_ankle_y = (left_ankle[1] + right_ankle[1]) / 2
                            else:
                                self.prev_ankle_y = y2

                            # 키 보정 적용: 실제 키에 따라 거리 계산 보정
                            height_correction = self.human_height_cm / self.reference_height_cm
                            self.k_constant = self.initial_distance_cm * self.prev_height_px * height_correction

                            self.root.after(0, lambda: self.lbl_status.config(text="측정중..."))

                    else:
                        # 이전 프레임의 사람 추적
                        best_box = None
                        best_keypoints = None
                        best_score = -1

                        prev_cx = (self.first_person_box[0] + self.first_person_box[2]) // 2
                        prev_cy = (self.first_person_box[1] + self.first_person_box[3]) // 2

                        for idx, box in enumerate(boxes_data):
                            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                            conf = float(box.conf[0].cpu().numpy())
                            curr_box = (x1, y1, x2, y2)

                            if not self.is_valid_person(curr_box, h, w, conf):
                                continue

                            cx, cy = (x1+x2)//2, (y1+y2)//2
                            iou = self.calc_iou(self.first_person_box, curr_box)
                            dist = np.sqrt((cx - prev_cx)**2 + (cy - prev_cy)**2)
                            dist_score = 1 / (1 + dist/100)

                            score = iou * 0.4 + dist_score * 0.4 + conf * 0.2

                            if score > best_score:
                                best_score = score
                                best_box = curr_box
                                best_keypoints = keypoints_data[idx]

                        if best_score >= 0.1:
                            target_box = best_box
                            target_keypoints = best_keypoints

            if target_box and target_keypoints is not None and not self.measurement_done:
                x1, y1, x2, y2 = target_box
                person_height_px = y2 - y1

                self.first_person_box = target_box
                self.prev_keypoints = target_keypoints

                # 발목 키포인트로 정확한 발 위치 계산 (신뢰도 가중 평균)
                left_ankle = target_keypoints[15]
                right_ankle = target_keypoints[16]

                # 1. 신뢰도 가중 평균으로 발목 Y 계산
                weighted_ankle_y = self.get_weighted_ankle_y(left_ankle, right_ankle)

                if weighted_ankle_y is not None:
                    # 2. 이상치 검출 - 급격한 변화 제거
                    if self.prev_ankle_y is not None and self.is_outlier(self.prev_ankle_y, weighted_ankle_y, self.outlier_threshold_ankle):
                        # 이상치면 이전 값 유지
                        ankle_y = self.prev_ankle_y
                    else:
                        # 3. 시간적 스무딩 적용
                        ankle_y = self.smooth_value(self.ankle_y_buffer, weighted_ankle_y, self.smoothing_window)

                    # 발목 X 계산 (신뢰도 가중)
                    left_conf = left_ankle[2]
                    right_conf = right_ankle[2]
                    if left_conf > 0.3 and right_conf > 0.3:
                        total_conf = left_conf + right_conf
                        ankle_x = (left_ankle[0] * left_conf + right_ankle[0] * right_conf) / total_conf
                    elif left_conf > 0.3:
                        ankle_x = left_ankle[0]
                    else:
                        ankle_x = right_ankle[0]
                else:
                    ankle_y = y2
                    ankle_x = (x1 + x2) / 2

                # 픽셀 높이에도 이상치 제거 및 스무딩 적용
                if self.prev_height_px is not None and self.is_outlier(self.prev_height_px, person_height_px, self.outlier_threshold_height):
                    # 이상치면 이전 값 유지
                    smoothed_height_px = self.prev_height_px
                else:
                    # 스무딩 적용
                    smoothed_height_px = self.smooth_value(self.height_buffer, person_height_px, self.smoothing_window)

                # 발목 좌표 기록 (그래프용)
                if self.measurement_started:
                    elapsed = (self.frame_count - self.start_frame) / self.fps
                    self.ankle_history_time.append(elapsed)
                    self.ankle_history_left_y.append(left_ankle[1] if left_ankle[2] > 0.5 else 0)
                    self.ankle_history_right_y.append(right_ankle[1] if right_ankle[2] > 0.5 else 0)
                    self.ankle_history_distance.append(self.total_distance_cm / 100)  # m 단위

                if self.prev_height_px is not None and smoothed_height_px > 0:
                    prev_distance = self.k_constant / self.prev_height_px
                    curr_distance = self.k_constant / smoothed_height_px

                    delta_distance = curr_distance - prev_distance

                    if delta_distance > 0:
                        self.total_distance_cm += delta_distance

                        if self.total_distance_cm >= 1000 and not self.measurement_done:
                            self.measurement_done = True
                            self.result_time = (self.frame_count - self.start_frame) / self.fps
                            self.result_speed = 10.0 / self.result_time if self.result_time > 0 else 0

                            # 평가
                            if self.result_time < 10:
                                grade = "정상"
                                grade_color = '#2ecc71'
                            elif self.result_time < 20:
                                grade = "약간느림"
                                grade_color = '#f1c40f'
                            elif self.result_time < 30:
                                grade = "느림"
                                grade_color = '#e67e22'
                            else:
                                grade = "매우느림"
                                grade_color = '#e74c3c'

                            # 결과 표시
                            self.root.after(0, lambda: self.lbl_status.config(
                                text="10m 완료!", fg='#2ecc71'))
                            self.root.after(0, lambda t=self.result_time: self.lbl_time.config(
                                text=f"{t:.2f} 초"))
                            self.root.after(0, lambda s=self.result_speed: self.lbl_speed.config(
                                text=f"{s:.2f} m/s"))
                            self.root.after(0, lambda s=self.result_speed: self.lbl_speed_kmh.config(
                                text=f"{s*3.6:.2f} km/h"))
                            self.root.after(0, lambda g=grade, c=grade_color: self.lbl_grade.config(
                                text=f"평가: {g}", fg=c))

                            # 저장 여부 확인
                            self.root.after(0, lambda g=grade: self.ask_save_result(g))

                self.prev_ankle_y = ankle_y
                self.prev_height_px = smoothed_height_px  # 스무딩된 값 저장

                dist_m = self.total_distance_cm / 100
                self.root.after(0, lambda d=dist_m: self.lbl_distance.config(
                    text=f"{d:.2f} m"))

                # 스켈레톤 그리기
                self.draw_skeleton(frame, target_keypoints)

                # 바운딩 박스
                box_color = (0, 255, 0) if not self.measurement_done else (255, 0, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

                # 발목 위치 표시
                cv2.circle(frame, (int(ankle_x), int(ankle_y)), 10, (0, 0, 255), -1)

                # 원본 높이와 스무딩된 높이 함께 표시
                cv2.putText(frame, f"H:{int(smoothed_height_px)}px (raw:{person_height_px})", (x1, y1-10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

            dist_m = self.total_distance_cm / 100
            cv2.putText(frame, f"Distance: {dist_m:.2f}m / 10m", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

            if self.measurement_started and not self.measurement_done:
                elapsed = (self.frame_count - self.start_frame) / self.fps
                cv2.putText(frame, f"Time: {elapsed:.2f}s", (10, 70),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            elif self.measurement_done:
                cv2.putText(frame, f"DONE: {self.result_time:.2f}s", (10, 70),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

            # Pose 모드 표시
            cv2.putText(frame, "POSE MODE", (w-150, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # 발목 좌표 그래프 그리기
            if self.measurement_started:
                frame = self.draw_ankle_graph(frame)

            self.show_frame(frame)

            # 10m 완료 시 분석 종료
            if self.measurement_done:
                break

        self.cap.release()
        self.is_analyzing = False
        self.root.after(0, self.done)

    def add_result(self, grade):
        name = self.entry_name.get().strip()
        gender = self.gender_var.get()
        height = self.entry_height.get()
        time_str = f"{self.result_time:.2f}s"
        speed_str = f"{self.result_speed:.2f}"

        item_id = self.tree.insert('', 0, values=(name, gender, height, time_str, speed_str, grade))

        # 발목 데이터 저장
        self.ankle_data_per_measurement[item_id] = {
            'name': name,
            'gender': gender,
            'height': height,
            'time': list(self.ankle_history_time),
            'left_y': list(self.ankle_history_left_y),
            'right_y': list(self.ankle_history_right_y),
            'distance': list(self.ankle_history_distance)
        }

    def ask_save_result(self, grade):
        """분석 완료 후 저장 여부를 묻는 다이얼로그"""
        result = messagebox.askyesno(
            "결과 저장",
            f"측정이 완료되었습니다.\n\n"
            f"시간: {self.result_time:.2f}초\n"
            f"속도: {self.result_speed:.2f} m/s\n"
            f"평가: {grade}\n\n"
            f"이 결과를 저장하시겠습니까?"
        )
        if result:
            # 로컬 리스트에 추가
            self.add_result(grade)

            # Supabase에 저장
            ankle_data = {
                'time': self.ankle_history_time,
                'left_y': self.ankle_history_left_y,
                'right_y': self.ankle_history_right_y,
                'distance': self.ankle_history_distance
            }
            if self.save_measurement_to_db(self.result_time, self.result_speed, grade, ankle_data):
                messagebox.showinfo("저장 완료", "결과가 클라우드에 저장되었습니다.")
            else:
                messagebox.showinfo("저장 완료", "결과가 로컬에만 저장되었습니다.")

    def show_graph(self):
        """측정 기록을 그래프로 표시"""
        items = self.tree.get_children()
        if not items:
            messagebox.showwarning("경고", "표시할 데이터가 없습니다.")
            return

        # 데이터 수집
        names = []
        times = []
        speeds = []
        grades = []

        for item in reversed(items):  # 시간순 정렬
            values = self.tree.item(item)['values']
            names.append(str(values[0]))
            time_val = str(values[2]).replace('s', '')
            times.append(float(time_val))
            speeds.append(float(values[3]))
            grades.append(str(values[4]))

        # 평가에 따른 색상
        colors = []
        for grade in grades:
            if grade == '정상':
                colors.append('#2ecc71')
            elif grade == '약간느림':
                colors.append('#f1c40f')
            elif grade == '느림':
                colors.append('#e67e22')
            else:
                colors.append('#e74c3c')

        # 그래프 창 생성
        graph_window = tk.Toplevel(self.root)
        graph_window.title("측정 결과 그래프")
        graph_window.geometry("800x600")
        graph_window.configure(bg='#1a1a2e')

        # Figure 생성
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
        fig.patch.set_facecolor('#1a1a2e')

        # 시간 그래프
        ax1.bar(names, times, color=colors)
        ax1.set_ylabel('시간 (초)', fontsize=12)
        ax1.set_title('피험자별 측정 시간', fontsize=14, fontweight='bold')
        ax1.set_facecolor('#16213e')
        ax1.tick_params(colors='white')
        ax1.yaxis.label.set_color('white')
        ax1.title.set_color('white')
        ax1.spines['bottom'].set_color('white')
        ax1.spines['left'].set_color('white')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        for label in ax1.get_xticklabels():
            label.set_color('white')
        for label in ax1.get_yticklabels():
            label.set_color('white')

        # 10초 기준선
        ax1.axhline(y=10, color='#4ecca3', linestyle='--', label='정상 기준 (10초)')
        ax1.legend(facecolor='#16213e', edgecolor='white', labelcolor='white')

        # 속도 그래프
        ax2.bar(names, speeds, color=colors)
        ax2.set_ylabel('속도 (m/s)', fontsize=12)
        ax2.set_xlabel('피험자', fontsize=12)
        ax2.set_title('피험자별 보행 속도', fontsize=14, fontweight='bold')
        ax2.set_facecolor('#16213e')
        ax2.tick_params(colors='white')
        ax2.yaxis.label.set_color('white')
        ax2.xaxis.label.set_color('white')
        ax2.title.set_color('white')
        ax2.spines['bottom'].set_color('white')
        ax2.spines['left'].set_color('white')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        for label in ax2.get_xticklabels():
            label.set_color('white')
        for label in ax2.get_yticklabels():
            label.set_color('white')

        # 1.0 m/s 기준선
        ax2.axhline(y=1.0, color='#4ecca3', linestyle='--', label='정상 기준 (1.0 m/s)')
        ax2.legend(facecolor='#16213e', edgecolor='white', labelcolor='white')

        plt.tight_layout()

        # Tkinter에 그래프 삽입
        canvas = FigureCanvasTkAgg(fig, master=graph_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

        # 닫기 버튼
        btn_close = tk.Button(graph_window, text="닫기",
                             command=graph_window.destroy,
                             font=('맑은 고딕', 11),
                             bg='#e94560', fg='white',
                             relief='flat', cursor='hand2',
                             width=10)
        btn_close.pack(pady=10)

    def done(self):
        self.btn_upload.config(state=tk.NORMAL)
        self.progress.configure(value=100)

        if not self.measurement_done:
            dist_m = self.total_distance_cm / 100
            self.lbl_status.config(text=f"{dist_m:.2f}m (10m 미도달)", fg='#e74c3c')

    def show_frame(self, frame):
        # 현재 프레임 저장 (리사이즈 시 재표시용)
        self.current_frame = frame.copy()

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame_rgb.shape[:2]

        # 동적 크기 사용
        label_w = getattr(self, 'video_display_width', 840)
        label_h = getattr(self, 'video_display_height', 620)

        scale = min(label_w/w, label_h/h)
        new_w, new_h = int(w*scale), int(h*scale)

        frame_resized = cv2.resize(frame_rgb, (new_w, new_h))
        img = ImageTk.PhotoImage(Image.fromarray(frame_resized))
        self.video_label.imgtk = img
        self.video_label.config(image=img, text='')

    # ===== Supabase 환자 관리 메서드 =====

    def load_patients(self):
        """Supabase에서 환자 목록 로드"""
        try:
            response = supabase.table('patients').select('*').order('name').execute()
            self.patients = response.data
            self.update_patient_combobox()
        except Exception as e:
            print(f"환자 목록 로드 실패: {e}")
            self.patients = []

    def update_patient_combobox(self):
        """환자 콤보박스 업데이트"""
        if hasattr(self, 'patient_combo'):
            patient_names = ["-- 새 환자 --"] + [f"{p['name']} ({p.get('gender', '')}, {p.get('height_cm', '')}cm)" for p in self.patients]
            self.patient_combo['values'] = patient_names
            self.patient_combo.current(0)

    def on_patient_select(self, event=None):
        """환자 선택 시 정보 자동 입력"""
        idx = self.patient_combo.current()
        if idx == 0:  # 새 환자
            self.selected_patient_id = None
            self.entry_name.delete(0, tk.END)
            self.entry_height.delete(0, tk.END)
            self.entry_height.insert(0, "177")
            self.gender_var.set("남")
            self.btn_delete_patient.config(state='disabled')
            self.btn_history.config(state='disabled')
        else:
            patient = self.patients[idx - 1]
            self.selected_patient_id = patient['id']
            self.entry_name.delete(0, tk.END)
            self.entry_name.insert(0, patient.get('name', ''))
            self.entry_height.delete(0, tk.END)
            self.entry_height.insert(0, str(patient.get('height_cm', 177)))
            self.gender_var.set(patient.get('gender', '남'))
            self.btn_delete_patient.config(state='normal')
            self.btn_history.config(state='normal')

    def save_patient_to_db(self):
        """현재 입력된 환자 정보를 Supabase에 저장"""
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("경고", "이름을 입력하세요.")
            return None

        try:
            height = int(self.entry_height.get())
        except:
            height = 177

        gender = self.gender_var.get()

        try:
            if self.selected_patient_id:
                # 기존 환자 업데이트
                response = supabase.table('patients').update({
                    'name': name,
                    'gender': gender,
                    'height_cm': height
                }).eq('id', self.selected_patient_id).execute()
                patient_id = self.selected_patient_id
            else:
                # 새 환자 생성
                response = supabase.table('patients').insert({
                    'name': name,
                    'gender': gender,
                    'height_cm': height
                }).execute()
                patient_id = response.data[0]['id']
                self.selected_patient_id = patient_id

            self.load_patients()  # 목록 새로고침
            return patient_id
        except Exception as e:
            messagebox.showerror("오류", f"환자 저장 실패: {e}")
            return None

    def delete_patient_from_db(self):
        """선택된 환자 삭제"""
        if not self.selected_patient_id:
            return

        if not messagebox.askyesno("확인", "이 환자와 모든 측정 기록을 삭제하시겠습니까?"):
            return

        try:
            supabase.table('patients').delete().eq('id', self.selected_patient_id).execute()
            self.selected_patient_id = None
            self.load_patients()
            self.patient_combo.current(0)
            self.on_patient_select()
            messagebox.showinfo("완료", "환자가 삭제되었습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"환자 삭제 실패: {e}")

    def save_measurement_to_db(self, time_seconds, speed_ms, grade, ankle_data=None):
        """측정 결과를 Supabase에 저장"""
        # 환자 정보 먼저 저장/업데이트
        patient_id = self.save_patient_to_db()
        if not patient_id:
            return False

        try:
            video_name = os.path.basename(self.video_path) if self.video_path else None

            # numpy float32를 일반 float로 변환
            ankle_data_serializable = None
            if ankle_data:
                ankle_data_serializable = {
                    'time': [float(x) for x in ankle_data.get('time', [])],
                    'left_y': [float(x) for x in ankle_data.get('left_y', [])],
                    'right_y': [float(x) for x in ankle_data.get('right_y', [])],
                    'distance': [float(x) for x in ankle_data.get('distance', [])]
                }

            supabase.table('measurements').insert({
                'patient_id': patient_id,
                'time_seconds': float(time_seconds),
                'speed_ms': float(speed_ms),
                'grade': grade,
                'video_name': video_name,
                'ankle_data': json.dumps(ankle_data_serializable) if ankle_data_serializable else None
            }).execute()
            return True
        except Exception as e:
            messagebox.showerror("오류", f"측정 저장 실패: {e}")
            return False
            return False

    def show_add_patient_dialog(self):
        """새 환자 추가 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title("새 환자 추가")
        dialog.geometry("300x250")
        dialog.configure(bg='#1a1a2e')
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="새 환자 등록", font=('맑은 고딕', 14, 'bold'),
                bg='#1a1a2e', fg='white').pack(pady=(20, 15))

        # 이름
        name_frame = tk.Frame(dialog, bg='#1a1a2e')
        name_frame.pack(fill='x', padx=30, pady=5)
        tk.Label(name_frame, text="이름", bg='#1a1a2e', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=8, anchor='w').pack(side='left')
        name_entry = tk.Entry(name_frame, font=('맑은 고딕', 11),
                             bg='#2d3a4f', fg='white', insertbackground='white',
                             relief='flat', width=15)
        name_entry.pack(side='left', ipady=5)

        # 성별
        gender_frame = tk.Frame(dialog, bg='#1a1a2e')
        gender_frame.pack(fill='x', padx=30, pady=5)
        tk.Label(gender_frame, text="성별", bg='#1a1a2e', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=8, anchor='w').pack(side='left')
        gender_var = tk.StringVar(value="남")
        tk.Radiobutton(gender_frame, text="남", variable=gender_var, value="남",
                      bg='#1a1a2e', fg='white', selectcolor='#2d3a4f',
                      font=('맑은 고딕', 10)).pack(side='left')
        tk.Radiobutton(gender_frame, text="여", variable=gender_var, value="여",
                      bg='#1a1a2e', fg='white', selectcolor='#2d3a4f',
                      font=('맑은 고딕', 10)).pack(side='left')

        # 키
        height_frame = tk.Frame(dialog, bg='#1a1a2e')
        height_frame.pack(fill='x', padx=30, pady=5)
        tk.Label(height_frame, text="키(cm)", bg='#1a1a2e', fg='#bdc3c7',
                font=('맑은 고딕', 10), width=8, anchor='w').pack(side='left')
        height_entry = tk.Entry(height_frame, font=('맑은 고딕', 11),
                               bg='#2d3a4f', fg='white', insertbackground='white',
                               relief='flat', width=8)
        height_entry.pack(side='left', ipady=5)
        height_entry.insert(0, "170")

        def save_new_patient():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("경고", "이름을 입력하세요.")
                return
            try:
                height = int(height_entry.get())
            except:
                height = 170

            try:
                response = supabase.table('patients').insert({
                    'name': name,
                    'gender': gender_var.get(),
                    'height_cm': height
                }).execute()
                self.load_patients()
                dialog.destroy()
                messagebox.showinfo("완료", f"환자 '{name}'이(가) 등록되었습니다.")
            except Exception as e:
                messagebox.showerror("오류", f"환자 등록 실패: {e}")

        # 버튼
        btn_frame = tk.Frame(dialog, bg='#1a1a2e')
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="등록", command=save_new_patient,
                 font=('맑은 고딕', 10, 'bold'), bg='#27ae60', fg='white',
                 relief='flat', width=8, cursor='hand2').pack(side='left', padx=5)
        tk.Button(btn_frame, text="취소", command=dialog.destroy,
                 font=('맑은 고딕', 10), bg='#7f8c8d', fg='white',
                 relief='flat', width=8, cursor='hand2').pack(side='left', padx=5)

    def search_patient_records(self):
        """환자 이름으로 측정 기록 검색"""
        search_name = self.search_entry.get().strip()
        if not search_name:
            messagebox.showwarning("경고", "검색할 환자 이름을 입력하세요.")
            return

        try:
            # 환자 검색
            response = supabase.table('patients').select('*').ilike('name', f'%{search_name}%').execute()
            patients = response.data

            if not patients:
                messagebox.showinfo("알림", f"'{search_name}' 이름의 환자를 찾을 수 없습니다.")
                return

            if len(patients) > 1:
                # 여러 환자가 검색된 경우 선택 다이얼로그
                self.show_patient_select_dialog(patients)
            else:
                # 한 명만 검색된 경우 바로 표시
                self.load_patient_measurements(patients[0])

        except Exception as e:
            messagebox.showerror("오류", f"검색 실패: {e}")

    def show_patient_select_dialog(self, patients):
        """여러 환자 중 선택 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title("환자 선택")
        dialog.geometry("350x300")
        dialog.configure(bg='#1a1a2e')
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="여러 환자가 검색되었습니다.\n환자를 선택하세요.",
                font=('맑은 고딕', 11), bg='#1a1a2e', fg='white').pack(pady=15)

        listbox = tk.Listbox(dialog, font=('맑은 고딕', 11), bg='#2d3a4f', fg='white',
                            selectbackground='#4ecca3', height=8)
        listbox.pack(fill='both', expand=True, padx=20, pady=5)

        for p in patients:
            listbox.insert(tk.END, f"{p['name']} ({p.get('gender', '')}, {p.get('height_cm', '')}cm)")

        def select_patient():
            selection = listbox.curselection()
            if selection:
                self.load_patient_measurements(patients[selection[0]])
                dialog.destroy()

        tk.Button(dialog, text="선택", command=select_patient,
                 font=('맑은 고딕', 10, 'bold'), bg='#3498db', fg='white',
                 relief='flat', width=10, cursor='hand2').pack(pady=15)

    def load_patient_measurements(self, patient):
        """특정 환자의 측정 기록을 Treeview에 로드"""
        self.searched_patient_id = patient['id']
        self.searched_patient_name = patient['name']

        # 상태 레이블 업데이트
        self.search_status_label.config(
            text=f"🔍 {patient['name']} ({patient.get('gender', '')}, {patient.get('height_cm', '')}cm)")

        try:
            response = supabase.table('measurements').select('*').eq(
                'patient_id', patient['id']
            ).order('measured_at', desc=True).execute()
            measurements = response.data

            # Treeview 초기화
            for item in self.tree.get_children():
                self.tree.delete(item)

            # 측정 기록 표시
            for m in measurements:
                item_id = self.tree.insert('', 'end', values=(
                    patient['name'],
                    patient.get('gender', ''),
                    f"{patient.get('height_cm', '')}",
                    f"{m.get('time_seconds', 0):.2f}s",
                    f"{m.get('speed_ms', 0):.2f}",
                    m.get('grade', '')
                ))
                # 발목 데이터 저장 (그래프용)
                if m.get('ankle_data'):
                    try:
                        ankle_data = json.loads(m['ankle_data'])
                        self.ankle_data_per_measurement[item_id] = ankle_data
                    except:
                        pass

            if not measurements:
                messagebox.showinfo("알림", f"'{patient['name']}'의 측정 기록이 없습니다.")

        except Exception as e:
            messagebox.showerror("오류", f"기록 로드 실패: {e}")

    def show_all_records(self):
        """전체 기록 표시 (검색 필터 해제)"""
        self.searched_patient_id = None
        self.searched_patient_name = None
        self.search_status_label.config(text="")
        self.search_entry.delete(0, tk.END)

        # Treeview 초기화 후 로컬 리스트 다시 표시
        for item in self.tree.get_children():
            self.tree.delete(item)

        for result in self.results_list:
            item_id = self.tree.insert('', 0, values=(
                result['name'],
                result.get('gender', ''),
                result.get('height', ''),
                f"{result['time']:.2f}s",
                f"{result['speed']:.2f}",
                result['grade']
            ))

    def show_patient_history(self):
        """환자 측정 히스토리 팝업"""
        if not self.selected_patient_id:
            messagebox.showwarning("경고", "환자를 먼저 선택하세요.")
            return

        # 해당 환자의 측정 기록 조회
        try:
            response = supabase.table('measurements').select('*').eq(
                'patient_id', self.selected_patient_id
            ).order('measured_at', desc=True).execute()
            measurements = response.data
        except Exception as e:
            messagebox.showerror("오류", f"기록 조회 실패: {e}")
            return

        if not measurements:
            messagebox.showinfo("알림", "이 환자의 측정 기록이 없습니다.")
            return

        # 히스토리 팝업 창
        history_win = tk.Toplevel(self.root)
        history_win.title(f"측정 히스토리 - {self.entry_name.get()}")
        history_win.geometry("800x500")
        history_win.configure(bg='#1a1a2e')

        # 상단: 기록 테이블
        table_frame = tk.Frame(history_win, bg='#16213e')
        table_frame.pack(fill='x', padx=10, pady=10)

        columns = ('date', 'time', 'speed', 'grade')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=8)
        tree.heading('date', text='측정일')
        tree.heading('time', text='시간(초)')
        tree.heading('speed', text='속도(m/s)')
        tree.heading('grade', text='평가')

        tree.column('date', width=150, anchor='center')
        tree.column('time', width=100, anchor='center')
        tree.column('speed', width=100, anchor='center')
        tree.column('grade', width=100, anchor='center')

        for m in measurements:
            date_str = m['measured_at'][:10] if m.get('measured_at') else '-'
            tree.insert('', 'end', values=(
                date_str,
                f"{m.get('time_seconds', 0):.2f}",
                f"{m.get('speed_ms', 0):.2f}",
                m.get('grade', '-')
            ))

        tree.pack(fill='x', padx=5, pady=5)

        # 하단: 트렌드 그래프
        graph_frame = tk.Frame(history_win, bg='#1a1a2e')
        graph_frame.pack(fill='both', expand=True, padx=10, pady=10)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5), facecolor='#1a1a2e')

        # 데이터 준비 (오래된 순으로 정렬)
        measurements_sorted = sorted(measurements, key=lambda x: x.get('measured_at', ''))
        dates = [m['measured_at'][:10] if m.get('measured_at') else '' for m in measurements_sorted]
        times = [m.get('time_seconds', 0) for m in measurements_sorted]
        speeds = [m.get('speed_ms', 0) for m in measurements_sorted]

        # 시간 그래프
        ax1.set_facecolor('#16213e')
        ax1.plot(range(len(times)), times, 'o-', color='#4ecca3', linewidth=2, markersize=8)
        ax1.set_xlabel('측정 회차', color='white')
        ax1.set_ylabel('시간 (초)', color='white')
        ax1.set_title('시간 변화 추이', color='white', fontsize=12)
        ax1.tick_params(colors='white')
        ax1.grid(True, alpha=0.3)
        for spine in ax1.spines.values():
            spine.set_color('#4ecca3')

        # 속도 그래프
        ax2.set_facecolor('#16213e')
        ax2.plot(range(len(speeds)), speeds, 's-', color='#e94560', linewidth=2, markersize=8)
        ax2.set_xlabel('측정 회차', color='white')
        ax2.set_ylabel('속도 (m/s)', color='white')
        ax2.set_title('속도 변화 추이', color='white', fontsize=12)
        ax2.tick_params(colors='white')
        ax2.grid(True, alpha=0.3)
        for spine in ax2.spines.values():
            spine.set_color('#e94560')

        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = App()
    app.run()
