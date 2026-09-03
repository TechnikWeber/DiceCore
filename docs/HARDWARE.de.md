[English](HARDWARE.md) · **Deutsch**

# Hardware

Was wohin gehört und was jede Entscheidung kostet. Gebaut ist davon noch nichts — das ist
der Plan, gegen den die Software geschrieben ist, und er wird korrigiert, sobald echte Teile
ankommen.

## Die kurze Fassung

| Teil | Wahl | Warum |
|---|---|---|
| Rechner | **Pi 4 (2 GB+) oder Pi 5** | Führt ein trainiertes Modell lokal in wenigen ms aus |
| | Pi Zero 2 W | Geht, aber auf einer stärkeren Maschine lesen (`engine.mode=remote`) |
| | Pi 3 / Pi Zero v1 | Nur Aufnahme — siehe *ARMv6 und ARMv7* unten |
| Kamera | **Camera Module 3 (IMX708)** | Autofokus, wird selbst erkannt, 12 MP reichen dicke |
| | Arducam 16MP IMX519 | Autofokus, schärfer, braucht ein `dtoverlay` und die mitgelieferte Tuning-Datei |
| | HQ Camera (IMX477) + 6-mm-Objektiv | Wenn die Kamera weit weg von der Fläche sitzen muss |
| | Beliebige USB-Webcam | `capture.source=v4l2`, für den ersten Aufbau völlig in Ordnung |
| Licht | Zwei kleine LEDs im flachen Winkel | Killt den Glanzfleck, der die Augen verdeckt |
| Montage | Kamera **senkrecht von oben** auf die Fläche | Jede Ziffer bleibt lesbar |

## Welcher Raspberry Pi

Die interessante Einschränkung ist nicht die Geschwindigkeit, sondern welche Pakete es für
die Architektur überhaupt gibt.

| Modell | Arch | numpy/OpenCV | onnxruntime | PyTorch | Was er kann |
|---|---|---|---|---|---|
| Pi 5, Pi 4 | arm64 | ja | ja | ja (langsam) | Alles, Modell inklusive |
| Pi 3, Zero 2 W (64-Bit-OS) | arm64 | ja | ja | mühsam | Klassisch + Modell; woanders trainieren |
| Pi 3, Zero 2 W (32-Bit-OS) | armv7 | ja | ja | nein | Klassisch + Modell; woanders trainieren |
| **Pi Zero v1, Pi 1** | **armv6** | **nein**¹ | **nein** | nein | **Nur Aufnahme** |

¹ piwheels hat armv6-Builds von numpy, aber kein modernes OpenCV. Geh von keinem
Bildverarbeitungs-Stack aus.

**Deshalb gibt es die geteilte Installation.** Auf einem ARMv6-Zero DiceCore ganz ohne Extras
installieren, `capture.source=rpicam` und `engine.mode=remote` setzen und `engine.remote_url`
auf einen Pi 5 oder einen PC zeigen lassen, auf dem DiceCore ebenfalls läuft. Der Zero nimmt
ein JPEG direkt aus `rpicam-still` auf — ohne numpy, ohne OpenCV — und schickt es an
`/api/v1/detect`. Die Antwort ist identisch mit einem lokalen Lesen, also merkt nichts, was
die API benutzt, einen Unterschied.

Andersherum geht es auch: das ganze DiceCore auf einem PC laufen lassen und dem Pi nichts
geben als ein Aufnahmeskript, das an `/api/v1/frame` schickt.

## Kameras

DiceCore behandelt „welcher Sensor" als Konfiguration, weil es auf einem Pi tatsächlich eine
ist. Die vier offiziellen Module findet `camera_auto_detect=1`. Alles andere braucht
`camera_auto_detect=0` plus ein ausdrückliches `dtoverlay=` in `/boot/firmware/config.txt`
und einen Neustart — das Feld **Camera → CSI camera module** schreibt das für dich und sagt
es dir auch.

| Modul | Overlay | Anmerkungen |
|---|---|---|
| Camera Module 1/2/3, HQ | *(automatisch)* | OV5647, IMX219, IMX708, IMX477 |
| **Arducam 16MP IMX519** | `imx519` | Autofokus braucht eine Tuning-Datei mit `rpi.af` |
| Arducam 64MP Hawkeye | `arducam-64mp` | Autofokus |
| Arducam 64MP Owlsight | `ov64a40` | Autofokus |
| Arducam Pivariety | `arducam-pivariety` | Antwortet auf I²C 0x0c |
| Irgendetwas anderes | *(selbst eintippen)* | Wird zuerst gegen `/boot/firmware/overlays` geprüft |

### Die Autofokus-Falle des IMX519

Die Tuning-Datei `imx519.json` von Raspberry Pi enthält keinen `rpi.af`-Algorithmus, also
beantwortet libcamera jede Fokusanfrage mit *no AF algorithm available*, und das Objektiv
bleibt, wo es gerade steht. Das sieht nicht nach kaputtem Fokus aus — es sieht nach einem
weichen Objektiv aus. Die Lösung ist eine Tuning-Datei mit `rpi.af`-Block; wie eine auf die
Kiste kommt, steht in `provisioning/tuning/README.md`. Sobald sie unter
`/var/lib/dicecore/tuning/imx519-af.json` liegt, setzt die Modulauswahl
`capture.tuning_file` darauf. Dann einen Fokusmodus aussuchen: über einer Würfelfläche ist
`manual` mit fester Dioptrie besser, denn `continuous` sucht bei jeder Würfelbewegung neu,
und Suchen ist genau das, was man mitten im Wurf nicht will.

**Eine Tuning-Datei wird nur gesetzt, wenn sie auch wirklich da ist.** Das ist keine
Höflichkeit. libcamera fällt nicht auf das Standard-Tuning zurück, wenn die angegebene Datei
fehlt — es lädt die IPA nicht, verwirft den Sensor, und `rpicam-still` meldet *no cameras
available*. Eine völlig intakte Arducam zeigt dann sämtliche Symptome eines nicht
gesteckten Flachbandkabels, wegen eines Textfelds. **Modul anwenden** schreibt den Pfad also
nur, wenn die Datei existiert, und sagt im selben Atemzug, dass der Autofokus so lange aus
ist. Ein weiches Bild ist ein viel kleineres Problem als gar kein Bild.

### Neu starten

**Camera → CSI-Kameramodul → Jetzt neu starten**, oder **System → Pi neu starten**. Ein in
`config.txt` geschriebenes Modul tut nichts, bevor die Firmware sie wieder gelesen hat, und
die Kiste hat normalerweise weder Tastatur noch Bildschirm — die Seite, auf der man gerade
ist, ist der Weg zurück hinein. **System → DiceCore neu starten** lädt nur den Dienst neu,
und das ist es, was ein frisch installiertes Paket oder ein geholtes Update braucht.

### Wenn keine Kamera gefunden wird

Der Reiter **Camera** sagt, welcher Fall es ist, aber kurz gefasst:

1. Flachbandkabel: Kontakte zur HDMI-Seite, im **CAM**-Port, nicht in DISPLAY.
2. `rpicam-hello --list-cameras` listet nichts → falsches Modul gewählt, oder die
   Auto-Erkennung ist für einen Sensor an, den sie nicht kennt.
3. `sudo i2cdetect -y 10` schweigt auch (braucht `dtparam=i2c_vc=on`) → es ist das Kabel.

## Montage über dem Turm

- **Senkrecht von oben.** Jede Neigung macht aus der Oberseite eines d20 ein Trapez und die
  umliegenden Flächen größer als die, auf die es ankommt.
- **Weit genug weg, dass die ganze Fläche mit Rand ins Bild passt**, dann in der Oberfläche
  mit dem Flächen-Rechteck beschneiden. Ein halb aus dem Bild ragender Würfel ist eine
  falsche Zahl, keine fehlende.
- **Fest.** Alles, was die Erkennung über deinen Aufbau lernt — die Fläche, die Würfelgröße,
  das Modell — setzt voraus, dass die Kamera sich nicht bewegt. Schraub sie fest; klemm sie
  nicht an die Wand des Turms selbst, die bei jedem Wurf federt.
- Die Landefläche sollte **matt und schlicht** sein und sich von den Würfeln abheben: dunkle
  Fläche für weiße Würfel. Filz schlägt Acryl; Acryl spiegelt die Lampe direkt ins Objektiv.
- Grob 25–35 cm von der Fläche zum Objektiv rahmt mit einem Standardmodul eine 15 × 15 cm
  große Fläche gut ein.

## Licht

Zwei kleine LED-Streifen oder Lampen im **flachen Winkel von gegenüberliegenden Seiten**.
Licht von oben setzt einen Glanzfleck mitten auf jeden Würfel, genau dort, wo die Augen sind,
und ein Ringlicht um das Objektiv macht dasselbe, nur teurer. Flach und von zwei Seiten hält
außerdem die Schatten kurz, und das ist wichtig, weil ein langer Schatten als Teil der
Würfelkontur gelesen wird.

Was auch immer du wählst: halt es **konstant**. Ein Modell, das unter einer Schreibtischlampe
trainiert und bei Tageslicht benutzt wird, ist ein Modell, das auf die Schreibtischlampe
trainiert wurde.

## Farben

DiceCore kann zu jedem Würfel auch die Farbe nennen — rot, blau, weiß, schwarz und den Rest —
unter **Detection → Classic engine**. Standardmäßig aus, weil es pro Würfel etwas Arbeit
kostet und den meisten Spielen egal ist; schalt es für die Spiele ein, in denen es *um* die
Farben geht, oder um auf einer gemeinsamen Fläche die Würfel des einen von denen des anderen
zu unterscheiden.

Es will dasselbe wie alles andere hier: gleichmäßiges Licht und eine Fläche, die den Würfeln
nicht gleicht. Ein schwarzer Würfel auf schwarzer Fläche ist für eine Kamera unsichtbar und
für einen Menschen auch, und dafür kann keine Erkennung etwas.

## Die Fläche einmessen

Einmalig, im Reiter **Detection**:

1. **Zieh ein Rechteck** über das Bild unter *Detection → Tray*, das die Landefläche abdeckt
   und sonst nichts. Die vier Anteile ergeben sich daraus; es ist nichts einzutippen. Alles
   außerhalb des Rechtecks wird abgedunkelt, damit sichtbar statt bloß gemeint ist, was die
   Erkennung ignorieren wird.

   ![Der Flächen-Editor: das Kamerabild mit einem Viertelraster darüber und einem gezogenen Rechteck über der Landefläche, alles außerhalb abgedunkelt](screenshots/tray.jpg)
2. Miss einen Würfel mit dem Lineal (ein normaler d6 hat 16 mm) und lies seine Pixelbreite
   aus einem aufgenommenen Bild ab. `mm_per_px = 16 / Pixel`. Damit kann die Erkennung die
   physische Größe als Hinweis benutzen, um Würfelarten zu unterscheiden.

Beides sind Anteile und Verhältnisse, also überleben sie einen Auflösungswechsel.
