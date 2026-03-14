# Bibliotecas ESSENCIAIS para o funcionamento do código
import RPi.GPIO as GPIO
import time
from mpd import MPDClient
import os

# === PINOS (BCM) ===
S0 = 5
S1 = 6
S2 = 13
S3 = 19
OUT = 26
BUTTON = 21

# === MÚSICAS ===
MUSICAS = {
    "BRANCO": "LavaChicken.mp3",
    "PRETO": "Stal.mp3",
    "VERMELHO": "Blocks.mp3",
    "VERDE": "Cat.mp3",
    "AZUL": "Relic.mp3",
    "AMARELO": "Pigstep.mp3",
    "CIANO": "Creator.mp3",
    "ROXO": "Otherside.mp3",
    "LARANJA": "Wait.mp3",
    "MARROM": "Far.mp3"
}

# === VARIÁVEIS DE ESTADO ===
jukebox_ligada = False
ultima_cor = None
ultima_leitura_botao = 1
tempo_ultimo_toggle = 0
musica_tocando = None

# === MPD CLIENT ===
client = MPDClient()
client.timeout = 10
client.idletimeout = None


def conectar_mpd():
    try:
        client.connect("localhost", 6600)
        print("Conectado ao MPD.")
        return True
    except Exception as e:
        print(f"Falha ao conectar MPD: {e}")
        return False


def verificar_conexao_mpd():
    try:
        client.ping()
        return True
    except Exception:
        try:
            client.disconnect()
        except:
            pass
        return conectar_mpd()


# === CONFIGURAÇÃO GPIO ===
def configurar_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(S0, GPIO.OUT)
    GPIO.setup(S1, GPIO.OUT)
    GPIO.setup(S2, GPIO.OUT)
    GPIO.setup(S3, GPIO.OUT)
    GPIO.setup(OUT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.output(S0, GPIO.HIGH)
    GPIO.output(S1, GPIO.HIGH)


""" === SENSOR DE COR ===
(Tem um toque de IA por ter me dado muita dor de cabeça fazendo essa parte)
"""

def get_frequency_polling(s2_state, s3_state, window_s=0.12):
    GPIO.output(S2, s2_state)
    GPIO.output(S3, s3_state)
    time.sleep(0.03)
    end = time.time() + window_s
    prev = GPIO.input(OUT)
    count = 0
    while time.time() < end:
        cur = GPIO.input(OUT)
        if prev == 1 and cur == 0:
            count += 1
        prev = cur
    return count / window_s if window_s > 0 else 0.0


def read_rgb(samples=3, window_s=0.10):
    r_total = g_total = b_total = 0.0
    for _ in range(samples):
        r = get_frequency_polling(GPIO.LOW, GPIO.LOW, window_s)
        g = get_frequency_polling(GPIO.HIGH, GPIO.HIGH, window_s)
        b = get_frequency_polling(GPIO.LOW, GPIO.HIGH, window_s)
        r_total += r
        g_total += g
        b_total += b
        time.sleep(0.01)
    return (r_total / samples, g_total / samples, b_total / samples)


# === IDENTIFICAÇÃO DE COR ===
def identificar_cor(r, g, b):
    cores_calibradas = {
        "VERMELHO": (6470, 1675, 2273),
        "VERDE": (4593, 7481, 3550),
        "AZUL": (1565, 2205, 2811),
        "AMARELO": (16385, 13120, 7060),
        "CIANO": (7075, 11191, 16646),
        "ROXO": (2706, 1761, 2765),
        "LARANJA": (17406, 3320, 3678),
        "MARROM": (2986, 1778, 1835),
        "BRANCO": (2897, 2868, 3383),
        "PRETO": (261, 235, 230)
    }

    menor_dif = float("inf")
    cor_identificada = None

    for cor_nome, (r_ref, g_ref, b_ref) in cores_calibradas.items():
        dist = ((r - r_ref)**2 + (g - g_ref)**2 + (b - b_ref)**2)**0.5
        if dist < menor_dif:
            menor_dif = dist
            cor_identificada = cor_nome

    print(f"R={r:.0f} G={g:.0f} B={b:.0f} → {cor_identificada} (dif={menor_dif:.0f})")
    if r < 500 and g < 500 and b < 500:
        return "PRETO"
    return cor_identificada


# === TOCAR MÚSICA ===
def tocar_musica_para_cor(cor):
    global musica_tocando
    nome = MUSICAS.get(cor)
    if not nome:
        if musica_tocando:
            try:
                client.stop()
            except:
                pass
            musica_tocando = None
            print("Parando música (sem mapeamento).")
        return

    if not verificar_conexao_mpd():
        print("MPD ainda não conectado.")
        return

    if musica_tocando == nome:
        return

    try:
        client.stop()
        client.clear()
        client.add(nome)
        client.play()
        musica_tocando = nome
        print(f"Tocando {nome} para cor {cor}")
    except Exception as e:
        print("Erro ao tocar via MPD:", e)


# === BOTÃO (Mais Estável) ===
def checar_botao_switch():
    global jukebox_ligada, ultima_leitura_botao, tempo_ultimo_toggle
    leitura_atual = GPIO.input(BUTTON)
    agora = time.time()

    # Detecta borda de descida (1→0)
    if leitura_atual == 0 and ultima_leitura_botao == 1:
        # Anti-repique e controle de tempo mínimo
        if agora - tempo_ultimo_toggle > 0.4:
            jukebox_ligada = not jukebox_ligada
            tempo_ultimo_toggle = agora
            if jukebox_ligada:
                print("\nJukebox LIGADA")
            else:
                print("\nJukebox DESLIGADA")
                try:
                    client.stop()
                except:
                    pass
                global musica_tocando
                musica_tocando = None

    ultima_leitura_botao = leitura_atual


# === MAIN ===
def main():
    global jukebox_ligada, musica_tocando
    configurar_gpio()
    conectar_mpd()
    print("=== Jukebox pronta (pressione o botão para ligar/desligar) ===")

    try:
        while True:
            checar_botao_switch()

            if not jukebox_ligada:
                time.sleep(0.1)
                continue

            verificar_conexao_mpd()
            r, g, b = read_rgb(samples=3, window_s=0.10)
            cor = identificar_cor(r, g, b)
            print("Cor detectada:", cor if cor else "Nenhuma")
            tocar_musica_para_cor(cor)
            time.sleep(0.25)

    except KeyboardInterrupt:
        print("\nEncerrando (CTRL+C).")
    finally:
        try:
            client.stop()
            client.clear()
            client.disconnect()
        except:
            pass
        GPIO.cleanup()
        print("GPIO liberado. Fim.")


if __name__ == "__main__":
    main()
