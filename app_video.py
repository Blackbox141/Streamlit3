import streamlit as st
import numpy as np
import cv2
from ultralytics import YOLO
import os
import requests
import chess
import chess.pgn
import tempfile
from PIL import Image
import time
import datetime

# Holen des aktuellen Skriptverzeichnisses
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Relativer Pfad zum Modell zur Erkennung der Schachfiguren
piece_model_path = os.path.join(BASE_DIR, 'Figure Detection', 'runs', 'detect', 'yolov8-chess28', 'weights', 'best.pt')

# Relativer Pfad zum Modell zur Erkennung der Eckpunkte
corner_model_path = os.path.join(BASE_DIR, 'Corner Detection', 'runs', 'detect', 'yolov8n_corner12', 'weights', 'best.pt')

# Relativer Pfad zum Modell zur Erkennung des Spielers am Zug (Schachuhr)
clock_model_path = os.path.join(BASE_DIR, 'Clock Detection 1', 'runs', 'detect', 'yolov8-chess3', 'weights', 'best.pt')

# Laden der YOLO-Modelle mit den relativen Pfaden
if os.path.exists(piece_model_path) and os.path.exists(corner_model_path) and os.path.exists(clock_model_path):
    piece_model = YOLO(piece_model_path)
    corner_model = YOLO(corner_model_path)
    clock_model = YOLO(clock_model_path)
else:
    st.error(f"Modelldatei nicht gefunden. Überprüfe die Pfade:\nPiece model: {piece_model_path}\nCorner model: {corner_model_path}\nClock model: {clock_model_path}")
    st.stop()

# FEN-Zeichen für Figuren
FEN_MAPPING = {
    'Black Pawn': 'p',
    'Black Bishop': 'b',
    'Black King': 'k',
    'Black Queen': 'q',
    'Black Rook': 'r',
    'Black Knight': 'n',
    'White Pawn': 'P',
    'White Bishop': 'B',
    'White King': 'K',
    'White Queen': 'Q',
    'White Rook': 'R',
    'White Knight': 'N'
}

# Festlegen der festen Werte für den Korrekturvektor
PERCENT_AB = 0.17  # Beispielwert: 17% der Strecke AB
PERCENT_BC = -0.07  # Beispielwert: -7% der Strecke BC

# Grundstellung FEN
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

def detect_pieces(image):
    results = piece_model.predict(image, conf=0.1, iou=0.3, imgsz=1400)
    class_names = piece_model.model.names  # Zugriff auf die Klassennamen
    result = results[0]

    midpoints = []
    labels = []
    boxes = result.boxes

    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        cls_id = int(box.cls.cpu().numpy()[0])
        label = class_names[cls_id]
        conf = box.conf.cpu().numpy()[0] * 100  # Confidence Score in Prozent

        # Berechnung des Mittelpunkts der unteren Hälfte der Bounding Box
        mid_x = x1 + (x2 - x1) / 2
        mid_y = y1 + (y2 - y1) * 0.75  # Mitte der unteren Hälfte

        midpoints.append([mid_x, mid_y])
        labels.append(label)

        # Zeichne die Bounding Box und das Label mit Confidence Score auf das Bild
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        text = f"{label}: {conf:.1f}%"
        cv2.putText(image, text, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1, cv2.LINE_AA)

    return np.array(midpoints), labels, image

def detect_corners(image):
    results = corner_model(image)
    class_names = corner_model.model.names  # Zugriff auf die Klassennamen
    points = {}

    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()  # (x1, y1, x2, y2)
        center_x = int((x1 + x2) / 2)  # Mittelpunkt der Bounding Box (x)
        center_y = int((y1 + y2) / 2)  # Mittelpunkt der Bounding Box (y)

        cls_id = int(box.cls.cpu().numpy()[0])

        # Klassennamen im YOLO-Modell zuordnen
        if cls_id == 0:  # A
            points["A"] = np.array([center_x, center_y])
        elif cls_id == 1:  # B
            points["B"] = np.array([center_x, center_y])
        elif cls_id == 2:  # C
            points["C"] = np.array([center_x, center_y])

        # Zeichne die Eckpunkte auf das Bild
        label = class_names[cls_id]
        cv2.circle(image, (center_x, center_y), 5, (0, 0, 255), -1)
        cv2.putText(image, label, (center_x + 10, center_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1, cv2.LINE_AA)

    if len(points) != 3:
        st.error("Nicht alle Eckpunkte (A, B, C) wurden erkannt!")
        st.stop()

    return points, image

def detect_player_turn(image):
    results = clock_model.predict(image, conf=0.1, iou=0.3, imgsz=1400)
    class_names = clock_model.model.names  # Zugriff auf die Klassennamen
    result = results[0]
    boxes = result.boxes

    # Initialisiere die Label-Liste
    labels = []

    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        cls_id = int(box.cls.cpu().numpy()[0])
        label = class_names[cls_id]
        labels.append(label)

        # Zeichne die Bounding Box und das Label auf das Bild
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 0), 2)
        cv2.putText(image, label, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1, cv2.LINE_AA)

    # Bestimme anhand der Labels, wer am Zug ist
    if 'left' in labels:
        player_turn = 'left'
    elif 'right' in labels:
        player_turn = 'right'
    else:
        player_turn = None  # Fordere Benutzereingabe

    # Überprüfe, ob 'hold' erkannt wurde
    if 'hold' in labels:
        player_turn = 'hold'

    return player_turn, image

def calculate_point_D(A, B, C):
    BC = C - B
    D_calculated = A + BC
    return D_calculated

def adjust_point_D(A, B, C, D_calculated, percent_AB, percent_BC):
    # Berechnung der Vektoren AB und BC
    AB = B - A
    BC = C - B

    # Berechnung des Korrekturvektors
    correction_vector = percent_AB * AB + percent_BC * BC

    # Anwenden des Korrekturvektors auf D_calculated
    D_corrected = D_calculated + correction_vector

    return D_corrected

def sort_points(A, B, C, D):
    points = np.array([A, B, C, D])
    # Sortiere die Punkte nach der y-Koordinate (oben und unten)
    points = sorted(points, key=lambda x: x[1])
    # Sortiere die oberen Punkte nach der x-Koordinate
    top_points = sorted(points[:2], key=lambda x: x[0])  # Obere Punkte (A und D)
    # Sortiere die unteren Punkte nach der x-Koordinate
    bottom_points = sorted(points[2:], key=lambda x: x[0])  # Untere Punkte (B und C)
    # Weisen den sortierten Punkten die richtige Position zu
    A_sorted, D_sorted = top_points  # A ist oben links, D ist oben rechts
    B_sorted, C_sorted = bottom_points  # B ist unten links, C ist unten rechts
    return np.array([A_sorted, B_sorted, C_sorted, D_sorted], dtype=np.float32)

def warp_perspective(image, src_points):
    dst_size = 800  # Zielgröße 800x800 Pixel für das quadratische Schachbrett
    dst_points = np.array([
        [0, 0],  # A' (oben links)
        [0, dst_size - 1],  # B' (unten links)
        [dst_size - 1, dst_size - 1],  # C' (unten rechts)
        [dst_size - 1, 0]  # D' (oben rechts)
    ], dtype=np.float32)

    # Perspektivtransformation berechnen
    M = cv2.getPerspectiveTransform(src_points, dst_points)

    # Perspektivtransformation anwenden
    warped_image = cv2.warpPerspective(image, M, (dst_size, dst_size))

    return warped_image, M

def generate_fen_from_board(midpoints, labels, grid_size=8, player_to_move='w'):
    # Erstelle ein leeres Schachbrett (8x8) als Liste von Listen
    board = [['' for _ in range(grid_size)] for _ in range(grid_size)]

    step_size = 800 // grid_size  # Größe jeder Zelle (entspricht der Größe des entzerrten Bildes)

    # Fülle das Board mit den Figuren basierend auf den erkannten Mittelpunkten
    for point, label in zip(midpoints, labels):
        x, y = point
        col = int(x // step_size)
        row = 7 - int(y // step_size)  # Invertiere die y-Achse

        # Prüfe, ob die Position innerhalb der Grenzen liegt
        if 0 <= row < grid_size and 0 <= col < grid_size:
            fen_char = FEN_MAPPING.get(label, '')
            board[row][col] = fen_char
        else:
            # Ignoriere Figuren außerhalb des Schachbretts
            pass

    # Erstelle die FEN-Notation
    fen_rows = []
    for row in board:
        fen_row = ''
        empty_count = 0
        for square in row:
            if square == '':
                empty_count += 1
            else:
                if empty_count > 0:
                    fen_row += str(empty_count)
                    empty_count = 0
                fen_row += square
        if empty_count > 0:
            fen_row += str(empty_count)
        fen_rows.append(fen_row)

    # Verbinde alle Zeilen mit Schrägstrichen und füge die zusätzlichen Informationen hinzu
    fen_string = '/'.join(fen_rows) + f" {player_to_move} - - 0 1"

    return fen_string

def analyze_fen_with_stockfish(fen, depth=15):
    url = 'https://stockfish.online/api/s/v2.php'

    # URL mit den Parametern FEN und Tiefe aufbauen
    params = {
        'fen': fen,
        'depth': min(depth, 15)  # Tiefe darf nicht größer als 15 sein
    }

    try:
        # Sende GET-Anfrage mit den Parametern
        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()  # Antwort im JSON-Format analysieren

            if data.get("success"):
                raw_best_move = data.get("bestmove", "None")
                evaluation = data.get("evaluation", "None")
                mate = data.get("mate", None)

                # Parsen des best_move Strings
                if raw_best_move != "None":
                    # Beispiel für raw_best_move: 'bestmove c3b4 ponder d7d6'
                    tokens = raw_best_move.split()
                    if len(tokens) >= 2:
                        best_move = tokens[1]  # Extrahiere den eigentlichen Zug
                    else:
                        best_move = None
                else:
                    best_move = None

                # Ausgabe der Ergebnisse
                st.write(f"\n**Stockfish Bewertung:**")
                st.write(f"**Beste Zugempfehlung:** {best_move}")
                st.write(f"**Bewertung:** {evaluation}")

                if mate is not None:
                    st.write(f"**Matt in:** {mate} Zügen")

                return best_move  # Rückgabe des besten Zugs
            else:
                st.error("Fehler in der API-Antwort:", data.get("error", "Unbekannter Fehler"))
        else:
            st.error(f"Fehler bei der Kommunikation mit der Stockfish API. Status code: {response.status_code}")
            st.error(f"Antwort: {response.text}")

    except Exception as e:
        st.error(f"Ein Fehler ist aufgetreten: {e}")

    return None  # Falls kein Zug empfohlen wurde

def plot_board_with_move(fen, best_move, white_side):
    import chess.svg

    board = chess.Board(fen)

    # Wenn ein bester Zug vorhanden ist, erstellen wir einen Pfeil
    if best_move:
        try:
            move = chess.Move.from_uci(best_move)
            arrows = [chess.svg.Arrow(move.from_square, move.to_square, color='#FF0000')]
        except ValueError:
            arrows = []
    else:
        arrows = []

    # Setze das Brett auf die entsprechende Perspektive
    if white_side == "Links":
        flipped = False  # Brett aus der Sicht von Weiß
    else:
        flipped = True  # Brett drehen

    # Erzeuge ein SVG-Bild des Schachbretts mit dem Pfeil
    board_svg = chess.svg.board(
        board=board,
        size=400,
        arrows=arrows,
        flipped=flipped,  # Brett drehen, wenn nötig
        coordinates=True
    )

    # Anzeige des SVG-Bildes in Streamlit
    st.components.v1.html(board_svg, height=500)

def save_game_to_pgn(moves, starting_fen):
    game = chess.pgn.Game()
    game.setup(chess.Board(starting_fen))

    node = game

    for move_uci in moves:
        move = chess.Move.from_uci(move_uci)
        node = node.add_variation(move)

    pgn_string = str(game)
    return pgn_string

def main():
    st.title("Schachspiel Analyse aus Video")

    # Video hochladen
    uploaded_file = st.file_uploader("Lade ein Video des Schachspiels hoch", type=["mp4", "avi", "mov"])

    if uploaded_file is not None:
        # Temporäre Datei erstellen
        tfile = tempfile.NamedTemporaryFile(delete=False)
        tfile.write(uploaded_file.read())

        cap = cv2.VideoCapture(tfile.name)

        # Framerate des Videos erhalten
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = int(fps) if fps > 0 else 25  # Standardmäßig 25, falls fps nicht ermittelt werden kann

        # Variablen initialisieren
        previous_player_turn = None
        previous_fen = None
        move_list = []
        game_started = False
        starting_position = None
        white_side = None
        user_white_side = None  # Variable, um zu speichern, ob der Benutzer die Seite gewählt hat
        game_over = False
        frame_count = 0

        # Einmalige Schachbrett-Erkennung
        ret, frame = cap.read()
        if not ret:
            st.error("Fehler beim Lesen des Videos.")
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Schritt 1: Erkennung der Eckpunkte
        detected_points, corner_image = detect_corners(frame_rgb)

        # Anzeige des Bildes mit den erkannten Eckpunkten
        st.image(corner_image, caption='Erkannte Eckpunkte', use_column_width=True)

        # Schritt 2: Berechnung der Ecke D und Perspektivtransformation
        A = detected_points["A"]
        B = detected_points["B"]
        C = detected_points["C"]
        D_calculated = calculate_point_D(A, B, C)

        # Anpassung des Punktes D mit dem festen Korrekturvektor
        D_corrected = adjust_point_D(A, B, C, D_calculated, PERCENT_AB, PERCENT_BC)

        # Sortiere die Punkte
        sorted_points = sort_points(A, B, C, D_corrected.astype(int))

        # Perspektivtransformation berechnen
        M = cv2.getPerspectiveTransform(sorted_points, np.array([
            [0, 0],
            [0, 799],
            [799, 799],
            [799, 0]
        ], dtype=np.float32))

        # Video zurücksetzen
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        # Video durchlaufen
        while cap.isOpened() and not game_over:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1

            # Analysiere nur jede Sekunde
            if frame_count % frame_interval != 0:
                continue  # Überspringe dieses Frame

            # Konvertiere das Frame in RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Kopie des Frames für die Anzeige
            display_frame = frame_rgb.copy()

            # Schritt 1: Erkennung der Schachuhr
            player_turn, clock_image = detect_player_turn(display_frame)

            # Anzeige des Bildes mit der Schachuhr
            st.image(clock_image, caption=f'Analysiertes Frame {frame_count} - Schachuhr', use_column_width=True)

            # Überprüfe, ob es einen Wechsel bei der Uhr gegeben hat
            if previous_player_turn != player_turn and player_turn != 'hold':
                # Uhrwechsel erkannt, Schachbrett analysieren

                # Schritt 2: Erkennung der Figuren
                piece_midpoints, piece_labels, piece_image = detect_pieces(display_frame)

                # Anzeige des Bildes mit den erkannten Figuren
                st.image(piece_image, caption=f'Analysiertes Frame {frame_count} - Figuren', use_column_width=True)

                # Transformiere die Figurenkoordinaten
                ones = np.ones((piece_midpoints.shape[0], 1))
                piece_midpoints_homogeneous = np.hstack([piece_midpoints, ones])
                transformed_midpoints = M @ piece_midpoints_homogeneous.T
                transformed_midpoints /= transformed_midpoints[2, :]  # Homogenisierung
                transformed_midpoints = transformed_midpoints[:2, :].T  # Zurück zu kartesischen Koordinaten

                # Jetzt versuchen wir beide Rotationen
                fen_found = False

                for side in ["Links", "Rechts"]:
                    if side == "Links":
                        # Weiß spielt links, keine Rotation
                        rotated_midpoints = transformed_midpoints.copy()
                    elif side == "Rechts":
                        # Weiß spielt rechts, Brett um 180 Grad drehen
                        rotated_midpoints = np.zeros_like(transformed_midpoints)
                        rotated_midpoints[:, 0] = 800 - transformed_midpoints[:, 0]
                        rotated_midpoints[:, 1] = 800 - transformed_midpoints[:, 1]
                    else:
                        rotated_midpoints = transformed_midpoints.copy()

                    # Generiere FEN
                    current_fen = generate_fen_from_board(rotated_midpoints, piece_labels)
                    st.write(f"**Aktuelle FEN-Notation ({side}):** {current_fen}")

                    # Prüfe, ob es die Grundstellung ist
                    if current_fen.startswith(STARTING_FEN):
                        game_started = True
                        starting_position = current_fen
                        white_side = side
                        fen_found = True
                        break

                if not fen_found:
                    # Fordere Benutzereingabe
                    if user_white_side is None:
                        st.write("Bitte wählen Sie, auf welcher Seite Weiß spielt:")
                        user_white_side = st.selectbox("Weiß spielt auf:", ("Links", "Rechts"))
                        white_side = user_white_side

                    # Rotierte Midpoints entsprechend der gewählten Seite
                    if white_side == "Links":
                        rotated_midpoints = transformed_midpoints.copy()
                    elif white_side == "Rechts":
                        rotated_midpoints = np.zeros_like(transformed_midpoints)
                        rotated_midpoints[:, 0] = 800 - transformed_midpoints[:, 0]
                        rotated_midpoints[:, 1] = 800 - transformed_midpoints[:, 1]
                    else:
                        rotated_midpoints = transformed_midpoints.copy()

                    # Generiere FEN erneut
                    current_fen = generate_fen_from_board(rotated_midpoints, piece_labels)
                    st.write(f"**Aktuelle FEN-Notation ({white_side}):** {current_fen}")
                    game_started = True
                    starting_position = current_fen

                # Speichere das aktuelle Frame (optional)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                image_path = f"schachbrett_{timestamp}.png"
                cv2.imwrite(image_path, cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR))
                st.write(f"Bild gespeichert: {image_path}")

                # Prüfe auf Schachmatt
                board = chess.Board(current_fen)
                if board.is_checkmate():
                    st.write("**Schachmatt!**")
                    if starting_position.startswith(STARTING_FEN):
                        # Wandle FEN in PGN um
                        pgn_string = save_game_to_pgn(move_list, starting_position)
                        st.write("**PGN des Spiels:**")
                        st.code(pgn_string)
                    else:
                        # Gehe zu Schritt 5
                        st.write("Das Spiel hat nicht von der Grundstellung begonnen.")
                        st.write("Glückwunsch zum Spielende!")
                    # Spiel sichern
                    game_over = True

                # Aktualisiere den vorherigen Spieler
                previous_player_turn = player_turn

            # Kurze Pause, um die GUI nicht zu überlasten
            time.sleep(0.1)

        cap.release()
        st.write("Videoverarbeitung abgeschlossen.")

    else:
        st.write("Bitte lade ein Video des Schachspiels hoch.")

if __name__ == "__main__":
    main()
