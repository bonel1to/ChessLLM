import pygame
import chess
import random
import pickle
import os
import sys
import openai
import math
from openrouter_config import OPENROUTER_API_KEY

# Инициализация Pygame
pygame.init()

# Получаем размеры экрана
info = pygame.display.Info()
SCREEN_WIDTH = info.current_w
SCREEN_HEIGHT = info.current_h

# Вычисляем размеры доски для полноэкранного режима
BOARD_SIZE = min(SCREEN_WIDTH, SCREEN_HEIGHT - 150)  # Оставляем место для информации
SQUARE_SIZE = BOARD_SIZE // 8

# Центрируем доску на экране
BOARD_OFFSET_X = (SCREEN_WIDTH - BOARD_SIZE) // 2
BOARD_OFFSET_Y = (SCREEN_HEIGHT - BOARD_SIZE - 150) // 2

# Создаем полноэкранное окно
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Шахматы с LLM ИИ - Полноэкранный режим")

# Цвета
LIGHT_SQUARE = (180, 175, 165)
DARK_SQUARE = (100, 140, 125)
HIGHLIGHT_COLOR = (255, 255, 0)
MOVE_HIGHLIGHT_COLOR = (100, 255, 0, 100) 
BACKGROUND_COLOR = (40, 40, 40)  

# Настройки анимации
ANIMATION_SPEED = 8     # Скорость анимации (пикселей за кадр)
ANIMATION_DURATION = 300  # Длительность анимации в миллисекундах

# Загрузка изображений фигур
PIECES = {}
assets_path = os.path.join(os.path.dirname(__file__), "assets")

for piece in ["bB", "bK", "bN", "bP", "bQ", "bR", "wB", "wK", "wN", "wP", "wQ", "wR"]:
    PIECES[piece] = pygame.transform.scale(
        pygame.image.load(os.path.join(assets_path, f"{piece}.png")), 
        (SQUARE_SIZE, SQUARE_SIZE)
    )

class AnimatedMove:
    """Класс для анимации движения фигур"""
    def __init__(self, piece_surface, start_pos, end_pos, duration=ANIMATION_DURATION):
        self.piece_surface = piece_surface
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.duration = duration
        self.start_time = pygame.time.get_ticks()
        self.is_finished = False
        
    def update(self):
        """Обновление позиции анимации"""
        current_time = pygame.time.get_ticks()
        elapsed = current_time - self.start_time
        
        if elapsed >= self.duration:
            self.is_finished = True
            return self.end_pos
        
        # Интерполяция позиции с easing (плавное замедление)
        progress = elapsed / self.duration
        # Применяем easing функцию для более плавной анимации
        eased_progress = 1 - (1 - progress) ** 3  # ease-out cubic
        
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * eased_progress
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * eased_progress
        
        return (x, y)
    
    def draw(self, screen):
        """Отрисовка анимированной фигуры"""
        if not self.is_finished:
            pos = self.update()
            screen.blit(self.piece_surface, pos)

class LLMAI:
    def __init__(self, model_name="meta-llama/llama-4-maverick-17b-128e-instruct:free"):
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        self.model_name = model_name
        self.move_count = 0

    def get_llm_move(self, board):
        """Получить ход от языковой модели"""
        self.move_count += 1
        
        # Получаем текущую позицию в FEN формате
        fen = board.fen()
        
        # Получаем историю ходов в PGN формате
        pgn_moves = []
        temp_board = chess.Board()
        
        # Воссоздаем историю ходов
        for move in board.move_stack:
            pgn_moves.append(temp_board.san(move))
            temp_board.push(move)
        
        pgn_history = " ".join(pgn_moves) if pgn_moves else "Начальная позиция"
        
        # Получаем список легальных ходов
        legal_moves = [move.uci() for move in board.legal_moves]
        legal_moves_str = ", ".join(legal_moves)
        
        # Создаем промпт для LLM
        prompt = f"""Ты играешь в шахматы как {'белые' if board.turn == chess.WHITE else 'черные'}.

Текущая позиция (FEN): {fen}
История ходов: {pgn_history}
Ход номер: {self.move_count}

Доступные ходы в UCI формате: {legal_moves_str}

Выбери ЛУЧШИЙ ход из доступных и верни ТОЛЬКО UCI код хода (например: e2e4, g1f3, e7e8q).
Не добавляй никаких объяснений, анализа или дополнительного текста.
Ответ должен содержать только UCI код хода."""

        messages = [
            {
                "role": "system", 
                "content": "Ты шахматный гроссмейстер. Твоя задача - выбрать лучший ход из предложенных вариантов и вернуть только UCI код этого хода."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ]

        try:
            print(f"Запрос к LLM для хода #{self.move_count}...")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=10
            )
            
            move_uci = response.choices[0].message.content.strip()
            print(f"LLM ответил: '{move_uci}'")
            
            # Проверяем, что ответ содержит только UCI код
            if move_uci in legal_moves:
                return move_uci
            else:
                print(f"LLM предложил недопустимый ход: {move_uci}")
                print(f"Доступные ходы: {legal_moves_str}")
                return None
                
        except Exception as e:
            print(f"Ошибка при запросе к LLM: {e}")
            return None

class ChessBoardGUI:
    def __init__(self):
        self.board = chess.Board()
        self.llm_ai = LLMAI()
        self.selected_square = None
        self.is_player_turn = True
        self.move_history = []
        self.clock = pygame.time.Clock()
        self.thinking = False
        self.last_ai_response = ""
        self.possible_moves_highlight = []
        
        # Анимация
        self.current_animation = None
        self.animation_in_progress = False
        self.last_move_squares = None  # Для подсветки последнего хода
        
    def square_to_pixel(self, square):
        """Преобразование квадрата доски в пиксельные координаты"""
        col = chess.square_file(square)
        row = 7 - chess.square_rank(square)
        return (BOARD_OFFSET_X + col * SQUARE_SIZE, BOARD_OFFSET_Y + row * SQUARE_SIZE)
    
    def pixel_to_square(self, pos):
        """Преобразование пиксельных координат в квадрат доски"""
        x, y = pos
        # Проверяем, что клик внутри доски
        if (x < BOARD_OFFSET_X or x >= BOARD_OFFSET_X + BOARD_SIZE or
            y < BOARD_OFFSET_Y or y >= BOARD_OFFSET_Y + BOARD_SIZE):
            return None
        
        col = (x - BOARD_OFFSET_X) // SQUARE_SIZE
        row = (y - BOARD_OFFSET_Y) // SQUARE_SIZE
        return chess.square(col, 7 - row)
    
    def animate_move(self, move):
        """Запуск анимации хода"""
        if self.animation_in_progress:
            return
            
        # Получаем фигуру, которая двигается
        piece = self.board.piece_at(move.from_square)
        if piece is None:
            return
            
        # Получаем изображение фигуры
        piece_char = piece.symbol()
        if piece_char.isupper():
            piece_name = "w" + piece_char.upper()
        else:
            piece_name = "b" + piece_char.upper()
        
        piece_surface = PIECES[piece_name]
        
        # Получаем начальную и конечную позиции
        start_pos = self.square_to_pixel(move.from_square)
        end_pos = self.square_to_pixel(move.to_square)
        
        # Создаем анимацию
        self.current_animation = AnimatedMove(piece_surface, start_pos, end_pos)
        self.animation_in_progress = True
        
        # Сохраняем квадраты для подсветки последнего хода
        self.last_move_squares = (move.from_square, move.to_square)

    def get_ai_move(self):
        """Получить ход от LLM ИИ"""
        if not self.board.is_game_over():
            self.thinking = True
            move_uci = self.llm_ai.get_llm_move(self.board)
            
            if move_uci:
                try:
                    move = chess.Move.from_uci(move_uci)
                    if move in self.board.legal_moves:
                        # Запускаем анимацию перед выполнением хода
                        self.animate_move(move)
                        self.board.push(move)
                        self.move_history.append(move.uci())
                        self.last_ai_response = f"LLM сделал ход: {move.uci()}"
                        print(self.last_ai_response)
                    else:
                        # Fallback к случайному ходу
                        move = random.choice(list(self.board.legal_moves))
                        self.animate_move(move)
                        self.board.push(move)
                        self.move_history.append(move.uci())
                        self.last_ai_response = f"LLM ошибся, случайный ход: {move.uci()}"
                        print(self.last_ai_response)
                except ValueError:
                    # Fallback к случайному ходу
                    move = random.choice(list(self.board.legal_moves))
                    self.animate_move(move)
                    self.board.push(move)
                    self.move_history.append(move.uci())
                    self.last_ai_response = f"LLM дал некорректный ответ, случайный ход: {move.uci()}"
                    print(self.last_ai_response)
            else:
                # Fallback к случайному ходу
                move = random.choice(list(self.board.legal_moves))
                self.animate_move(move)
                self.board.push(move)
                self.move_history.append(move.uci())
                self.last_ai_response = f"LLM не ответил, случайный ход: {move.uci()}"
                print(self.last_ai_response)
            
            self.thinking = False
        self.is_player_turn = True

    def draw_board(self):
        """Отрисовка шахматной доски"""
        for row in range(8):
            for col in range(8):
                color = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
                rect = pygame.Rect(
                    BOARD_OFFSET_X + col * SQUARE_SIZE, 
                    BOARD_OFFSET_Y + row * SQUARE_SIZE, 
                    SQUARE_SIZE, 
                    SQUARE_SIZE
                )
                pygame.draw.rect(SCREEN, color, rect)

        # Подсветка последнего хода
        if self.last_move_squares and not self.animation_in_progress:
            for square in self.last_move_squares:
                col = chess.square_file(square)
                row = 7 - chess.square_rank(square)
                # Создаем полупрозрачную поверхность для подсветки
                highlight_surface = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
                highlight_surface.fill((255, 255, 0, 80))  # Желтый с прозрачностью
                SCREEN.blit(highlight_surface, (BOARD_OFFSET_X + col * SQUARE_SIZE, BOARD_OFFSET_Y + row * SQUARE_SIZE))

        # Подсветка выбранной клетки
        if self.selected_square is not None:
            col = chess.square_file(self.selected_square)
            row = 7 - chess.square_rank(self.selected_square)
            rect = pygame.Rect(
                BOARD_OFFSET_X + col * SQUARE_SIZE, 
                BOARD_OFFSET_Y + row * SQUARE_SIZE, 
                SQUARE_SIZE, 
                SQUARE_SIZE
            )
            pygame.draw.rect(SCREEN, HIGHLIGHT_COLOR, rect, 3)

        # Подсветка возможных ходов
        for square in self.possible_moves_highlight:
            col = chess.square_file(square)
            row = 7 - chess.square_rank(square)
            highlight_surface = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
            pygame.draw.circle(highlight_surface, MOVE_HIGHLIGHT_COLOR, (SQUARE_SIZE // 2, SQUARE_SIZE // 2), SQUARE_SIZE // 4)
            SCREEN.blit(highlight_surface, (BOARD_OFFSET_X + col * SQUARE_SIZE, BOARD_OFFSET_Y + row * SQUARE_SIZE))

    def draw_pieces(self):
        """Отрисовка фигур на доске"""
        for row in range(8):
            for col in range(8):
                square = chess.square(col, 7 - row)
                piece = self.board.piece_at(square)
                
                # Не рисуем фигуру, если она участвует в анимации
                if (self.animation_in_progress and self.current_animation and 
                    self.last_move_squares and square in self.last_move_squares):
                    continue
                
                if piece:
                    piece_char = piece.symbol()
                    if piece_char.isupper():
                        piece_name = "w" + piece_char.upper()
                    else:
                        piece_name = "b" + piece_char.upper()
                    SCREEN.blit(PIECES[piece_name], (BOARD_OFFSET_X + col * SQUARE_SIZE, BOARD_OFFSET_Y + row * SQUARE_SIZE))

    def draw_animation(self):
        """Отрисовка анимации"""
        if self.current_animation and self.animation_in_progress:
            self.current_animation.draw(SCREEN)
            
            # Проверяем, завершилась ли анимация
            if self.current_animation.is_finished:
                self.animation_in_progress = False
                self.current_animation = None

    def draw_info(self):
        """Отрисовка информационной панели"""
        font_size = max(24, SCREEN_HEIGHT // 40)
        font = pygame.font.Font(None, font_size)
        
        info_y = BOARD_OFFSET_Y + BOARD_SIZE + 20
        
        # Информация о ходе
        if self.thinking:
            turn_text = "LLM ИИ думает..."
        elif self.animation_in_progress:
            turn_text = "Анимация хода..."
        elif self.board.is_game_over():
            result = self.board.result()
            if result == "1-0":
                turn_text = "Игра окончена: Белые победили (Мат)!"
            elif result == "0-1":
                turn_text = "Игра окончена: Черные победили (Мат)!"
            elif result == "1/2-1/2":
                if self.board.is_stalemate():
                    turn_text = "Игра окончена: Пат (Ничья)!"
                elif self.board.is_insufficient_material():
                    turn_text = "Игра окончена: Недостаточно материала (Ничья)!"
                elif self.board.is_fivefold_repetition():
                    turn_text = "Игра окончена: Пятикратное повторение (Ничья)!"
                elif self.board.is_seventyfive_moves():
                    turn_text = "Игра окончена: Правило 75 ходов (Ничья)!"
                else:
                    turn_text = "Игра окончена: Ничья!"
            else:
                turn_text = "Игра окончена: Неизвестный результат."
        elif self.board.turn == chess.WHITE:
            turn_text = "Ход белых (игрок)"
        else:
            turn_text = "Ход черных (LLM ИИ)"
        
        if not self.is_player_turn and not self.thinking and not self.animation_in_progress and not self.board.is_game_over():
            turn_text = "Ход LLM ИИ"
        
        text_surface = font.render(turn_text, True, (255, 255, 255))
        SCREEN.blit(text_surface, (BOARD_OFFSET_X, info_y))
        
        # Последний ход
        if self.move_history:
            last_move = f"Последний ход: {self.move_history[-1]}"
            text_surface = font.render(last_move, True, (255, 255, 255))
            SCREEN.blit(text_surface, (BOARD_OFFSET_X, info_y + 30))
        
        # Последний ответ ИИ
        if self.last_ai_response:
            # Обрезаем текст, если он слишком длинный
            max_chars = SCREEN_WIDTH // 12
            display_text = self.last_ai_response[:max_chars]
            text_surface = font.render(display_text, True, (200, 200, 200))
            SCREEN.blit(text_surface, (BOARD_OFFSET_X, info_y + 60))
        
        # Управление
        controls = [
            "N - Новая игра",
            "ESC - Выход"
        ]
        
        control_x = BOARD_OFFSET_X + BOARD_SIZE - 200
        for i, control_text in enumerate(controls):
            text_surface = font.render(control_text, True, (255, 255, 255))
            SCREEN.blit(text_surface, (control_x, info_y + i * 30))

    def handle_event(self, event):
        """Обработка событий Pygame"""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.is_player_turn and not self.thinking and not self.animation_in_progress:
                pos = pygame.mouse.get_pos()
                square = self.pixel_to_square(pos)
                
                if square is not None:
                    if self.selected_square is None:
                        # Выбрана фигура
                        piece = self.board.piece_at(square)
                        if piece and piece.color == self.board.turn:
                            self.selected_square = square
                            self.possible_moves_highlight = [
                                move.to_square for move in self.board.legal_moves 
                                if move.from_square == self.selected_square
                            ]
                    else:
                        # Сделан ход
                        move = chess.Move(self.selected_square, square)
                        if move in self.board.legal_moves:
                            self.animate_move(move)
                            self.board.push(move)
                            self.move_history.append(move.uci())
                            self.selected_square = None
                            self.possible_moves_highlight = []
                            self.is_player_turn = False
                        else:
                            # Попытка выбрать другую фигуру или отменить выбор
                            piece = self.board.piece_at(square)
                            if piece and piece.color == self.board.turn:
                                self.selected_square = square
                                self.possible_moves_highlight = [
                                    move.to_square for move in self.board.legal_moves 
                                    if move.from_square == self.selected_square
                                ]
                            else:
                                self.selected_square = None
                                self.possible_moves_highlight = []
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_n:
                self.board = chess.Board()
                self.llm_ai = LLMAI()
                self.selected_square = None
                self.is_player_turn = True
                self.move_history = []
                self.thinking = False
                self.last_ai_response = ""
                self.possible_moves_highlight = []
                self.current_animation = None
                self.animation_in_progress = False
                self.last_move_squares = None
            elif event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()

    def run(self):
        """Основной игровой цикл"""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                self.handle_event(event)

            SCREEN.fill(BACKGROUND_COLOR)
            self.draw_board()
            self.draw_pieces()
            self.draw_animation()
            self.draw_info()
            pygame.display.flip()

            if not self.is_player_turn and not self.animation_in_progress and not self.board.is_game_over():
                self.get_ai_move()

            self.clock.tick(60)  # Ограничение FPS

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    print("=== ШАХМАТЫ С LLM ИИ - ПОЛНОЭКРАННЫЙ РЕЖИМ ===")
    print("Вы играете белыми против языковой модели LLM")
    print("Игра запускается в полноэкранном режиме с плавными анимациями!")
    print("=== ШАХМАТЫ С LLM ИИ - ПОЛНОЭКРАННЫЙ РЕЖИМ ===")
    print("Игра запущена! Вы играете белыми против LLM ИИ.")
    print("Используйте мышь для ходов.")
    print("Управление: N - новая игра, ESC - выход")
    game_gui = ChessBoardGUI()
    game_gui.run()


