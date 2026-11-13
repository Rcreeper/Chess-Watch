import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import threading
import chess
import chess.engine
import math

# Update to your actual stockfish path using the raw string (r)
STOCKFISH_PATH = r"C:\Users\vinay\OneDrive\Desktop\Python Projects\stockfish\stockfish-windows-x86-64-universal.exe"

# Unicode mapping for 2D board rendering
PIECE_SYMBOLS = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚',
    '.': ''
}

def cp_to_win_prob(score: chess.engine.PovScore) -> float:
    if score.is_mate():
        mate_in = score.white().mate()
        return 100.0 if mate_in > 0 else 0.0
    cp = score.white().score()
    if cp is None:
        cp = 0
    cp = max(-2000, min(2000, cp))
    win_prob = 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)
    return round(win_prob, 1)

def analyze_position(board_fen_placement: str, stockfish_path: str):
    results = {"white": [], "black": [], "overall_verdict": ""}
    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        for color_name, turn in [("white", chess.WHITE), ("black", chess.BLACK)]:
            full_fen = f"{board_fen_placement} {'w' if turn == chess.WHITE else 'b'} KQkq - 0 1"
            board = chess.Board(full_fen)
            if not board.is_valid():
                full_fen = f"{board_fen_placement} {'w' if turn == chess.WHITE else 'b'} - - 0 1"
                board = chess.Board(full_fen)

            info = engine.analyse(board, chess.engine.Limit(time=0.4), multipv=2)
            for idx, line in enumerate(info):
                move = line["pv"][0]
                san_move = board.san(move)
                uci_move = move.uci() # e.g., 'e2e4'
                score = line["score"]
                white_win_prob = cp_to_win_prob(score)
                side_confidence = white_win_prob if turn == chess.WHITE else round(100.0 - white_win_prob, 1)
                
                results[color_name].append({
                    "rank": idx + 1,
                    "move": san_move,
                    "uci": uci_move,
                    "confidence": side_confidence
                })

    white_best_win = results["white"][0]["confidence"]
    if white_best_win > 55:
        results["overall_verdict"] = f"White is favored ({white_best_win}%)"
    elif white_best_win < 45:
        results["overall_verdict"] = f"Black is favored ({round(100 - white_best_win, 1)}%)"
    else:
        results["overall_verdict"] = "Position is balanced"
    return results

def uci_to_natural_language(board: chess.Board, uci_str: str) -> str:
    """Converts a UCI move like 'e2e4' into instruction style: 'White Pawn from e2 to e4'"""
    try:
        move = chess.Move.from_uci(uci_str)
        piece = board.piece_at(move.from_square)
        if not piece:
            return uci_str
        
        color_name = "White" if piece.color == chess.WHITE else "Black"
        piece_names = {
            chess.PAWN: "Pawn", chess.KNIGHT: "Knight", chess.BISHOP: "Bishop",
            chess.ROOK: "Rook", chess.QUEEN: "Queen", chess.KING: "King"
        }
        p_name = piece_names.get(piece.piece_type, "Piece")
        return f"{color_name} {p_name}: {uci_str[:2]} ➔ {uci_str[2:]}"
    except Exception:
        return uci_str

class ChessVisionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chess Vision Arcade AI")
        self.root.geometry("1260x740")
        self.root.configure(bg="#0f172a") # Arcade dark deep blue background
        
        self.cv_image = None
        self.current_board = chess.Board()

        # Custom Arcade Palette Styles
        self.bg_dark = "#0f172a"
        self.panel_bg = "#1e293b"
        self.accent_blue = "#38bdf8"
        self.text_white = "#f8fafc"
        self.btn_bg = "#0284c7"

        # ==================== LEFT PANEL (Image Upload & Display) ====================
        left_frame = tk.LabelFrame(root, text=" 📷 Source Photo / Webcam ", bg=self.panel_bg, fg=self.accent_blue, 
                                   padx=15, pady=15, font=("Courier New", 11, "bold"))
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=12)

        self.image_label = tk.Label(left_frame, text="NO IMAGE LOADED\n(Upload or Capture via Webcam)", 
                                    bg="#090d16", fg="#94a3b8", font=("Courier New", 10), width=45, height=26)
        self.image_label.pack(pady=10, fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(left_frame, bg=self.panel_bg)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="UPLOAD PHOTO", command=self.upload_image, bg=self.btn_bg, fg=self.text_white,
                  font=("Courier New", 9, "bold"), relief="raised", bd=3, width=15).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="WEBCAM", command=self.capture_webcam, bg=self.btn_bg, fg=self.text_white,
                  font=("Courier New", 9, "bold"), relief="raised", bd=3, width=12).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="ANALYZE BOARD", command=self.run_analysis_thread, 
                  bg="#10b981", fg=self.text_white, font=("Courier New", 9, "bold"), relief="raised", bd=3, width=15).grid(row=0, column=2, padx=5)

        # ==================== RIGHT PANEL (2D Board & Arcade Analysis) ====================
        right_outer_frame = tk.Frame(root, bg=self.bg_dark)
        right_outer_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=12, pady=12)

        # Top Right: 2D Digital Chessboard Canvas (Arcade Blue/White theme)
        board_frame = tk.LabelFrame(right_outer_frame, text=" ♟ AI RECOGNIZED 2D BOARD ", bg=self.panel_bg, fg=self.accent_blue, 
                                    padx=10, pady=10, font=("Courier New", 10, "bold"))
        board_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        self.board_canvas = tk.Canvas(board_frame, width=360, height=360, bg="#cbd5e1", highlightthickness=2, highlightbackground=self.accent_blue)
        self.board_canvas.pack(pady=5)
        self.draw_2d_board(self.current_board)

        # Bottom Right: Instructions & Engine Verdict
        analysis_frame = tk.LabelFrame(right_outer_frame, text=" ⚡ TACTICAL ADVICE ", bg=self.panel_bg, fg=self.accent_blue, 
                                       padx=15, pady=10, font=("Courier New", 10, "bold"))
        analysis_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        tk.Label(analysis_frame, text="MATCH VERDICT:", bg=self.panel_bg, fg=self.accent_blue, font=("Courier New", 9, "bold")).pack(anchor="w")
        self.verdict_label = tk.Label(analysis_frame, text="Waiting for analysis...", bg=self.panel_bg, fg=self.text_white, font=("Courier New", 10))
        self.verdict_label.pack(anchor="w", pady=(0, 8))

        # White Instructions Box
        w_box = tk.LabelFrame(analysis_frame, text=" WHITE MOVES (PLAY HERE) ", bg=self.panel_bg, fg="#e2e8f0", 
                              font=("Courier New", 9, "bold"), padx=10, pady=6)
        w_box.pack(fill=tk.X, pady=4)
        self.w_m1 = tk.Label(w_box, text="1st: -", bg=self.panel_bg, fg=self.text_white, font=("Courier New", 9))
        self.w_m1.pack(anchor="w", pady=1)
        self.w_m2 = tk.Label(w_box, text="2nd: -", bg=self.panel_bg, fg="#94a3b8", font=("Courier New", 9))
        self.w_m2.pack(anchor="w", pady=1)

        # Black Instructions Box
        b_box = tk.LabelFrame(analysis_frame, text=" BLACK MOVES (ALTERNATE) ", bg=self.panel_bg, fg="#e2e8f0", 
                              font=("Courier New", 9, "bold"), padx=10, pady=6)
        b_box.pack(fill=tk.X, pady=4)
        self.b_m1 = tk.Label(b_box, text="1st: -", bg=self.panel_bg, fg=self.text_white, font=("Courier New", 9))
        self.b_m1.pack(anchor="w", pady=1)
        self.b_m2 = tk.Label(b_box, text="2nd: -", bg=self.panel_bg, fg="#94a3b8", font=("Courier New", 9))
        self.b_m2.pack(anchor="w", pady=1)

        self.status_label = tk.Label(analysis_frame, text="STATUS: READY", bg=self.panel_bg, fg="#38bdf8", font=("Courier New", 9, "bold"))
        self.status_label.pack(side=tk.BOTTOM, anchor="w", pady=4)

    def draw_2d_board(self, board: chess.Board):
        """Draws an 8x8 arcade blue and white themed chessboard canvas."""
        self.board_canvas.delete("all")
        square_size = 45
        # Arcade blue tile theme (Dark slate blue vs ice blue)
        colors = ["#e0f2fe", "#0284c7"] 
        
        for r in range(8):
            for c in range(8):
                x1 = c * square_size
                y1 = r * square_size
                x2 = x1 + square_size
                y2 = y1 + square_size
                
                color = colors[(r + c) % 2]
                self.board_canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
                
                square_index = chess.square(c, 7 - r)
                piece = board.piece_at(square_index)
                
                if piece:
                    symbol = PIECE_SYMBOLS.get(piece.symbol(), "")
                    text_color = "#0f172a" if piece.color == chess.WHITE else "#ffffff"
                    shadow_color = "#94a3b8" if piece.color == chess.WHITE else "#000000"
                    
                    self.board_canvas.create_text(x1 + square_size/2 + 1, y1 + square_size/2 + 1, 
                                                  text=symbol, font=("Courier New", 22, "bold"), fill=shadow_color)
                    self.board_canvas.create_text(x1 + square_size/2, y1 + square_size/2, 
                                                  text=symbol, font=("Courier New", 22, "bold"), fill=text_color)

    def display_cv_image(self, cv_img):
        self.cv_image = cv_img
        rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
        pil_img.thumbnail((600, 600))
        tk_img = ImageTk.PhotoImage(pil_img)
        self.image_label.config(image=tk_img, text="", width=0, height=0)
        self.image_label.image = tk_img

    def upload_image(self):
        path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp")])
        if path:
            img = cv2.imread(path)
            self.display_cv_image(img)
            self.status_label.config(text="STATUS: IMAGE LOADED")

    def capture_webcam(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Camera Error", "Could not access webcam.")
            return
        messagebox.showinfo("Webcam", "Press SPACE to snap photo, or ESC to cancel.")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            cv2.imshow("Press SPACE to Capture", frame)
            key = cv2.waitKey(1)
            if key % 256 == 27:
                break
            elif key % 256 == 32:
                self.display_cv_image(frame)
                self.status_label.config(text="STATUS: CAPTURED FROM WEBCAM")
                break
        cap.release()
        cv2.destroyAllWindows()

    def predict_fen_from_image(self, cv_img) -> str:
        # Placeholder FEN placement for testing the pipeline
        return "r1bqk1nr/pppp1ppp/2n5/4p3/1bB1P3/5N2/PPPP1PPP/RNBQK2R"

    def run_analysis_thread(self):
        if self.cv_image is None:
            messagebox.showwarning("No Image", "Please upload or capture a photo first.")
            return
        self.status_label.config(text="STATUS: COMPUTING ENGINE...")
        threading.Thread(target=self.process_board_pipeline, daemon=True).start()

    def process_board_pipeline(self):
        try:
            fen_placement = self.predict_fen_from_image(self.cv_image)
            
            full_fen = f"{fen_placement} w KQkq - 0 1"
            temp_board = chess.Board(full_fen)
            self.current_board = temp_board
            self.root.after(0, lambda: self.draw_2d_board(self.current_board))

            results = analyze_position(fen_placement, STOCKFISH_PATH)
            self.root.after(0, lambda: self.update_results_ui(results, temp_board))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Analysis Error", str(e)))
            self.root.after(0, lambda: self.status_label.config(text="STATUS: ERROR OCCURRED"))

    def update_results_ui(self, results, board: chess.Board):
        self.verdict_label.config(text=results['overall_verdict'])
        
        w1, w2 = results["white"][0], results["white"][1]
        w1_text = uci_to_natural_language(board, w1['uci'])
        w2_text = uci_to_natural_language(board, w2['uci'])
        self.w_m1.config(text=f"1st: {w1_text} ({w1['confidence']}%)")
        self.w_m2.config(text=f"2nd: {w2_text} ({w2['confidence']}%)")

        b1, b2 = results["black"][0], results["black"][1]
        b_board = board.copy()
        if b_board.turn == chess.WHITE:
            b_board.turn = chess.BLACK
        b1_text = uci_to_natural_language(b_board, b1['uci'])
        b2_text = uci_to_natural_language(b_board, b2['uci'])
        self.b_m1.config(text=f"1st: {b1_text} ({b1['confidence']}%)")
        self.b_m2.config(text=f"2nd: {b2_text} ({b2['confidence']}%)")

        self.status_label.config(text="STATUS: ANALYSIS COMPLETE")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChessVisionApp(root)
    root.mainloop()