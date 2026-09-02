[English](TRAINING.md) · **Deutsch**

# DiceCore deine Würfel beibringen

Die klassische Erkennung zählt Augen und braucht nichts. Ziffern — ein d20, der 14 zeigt, ein
d10, der 7 zeigt — brauchen ein Modell, und ein Modell muss *deine* Würfel unter *deinem*
Licht gesehen haben. Das ist eine Sache von fünf Minuten, kein Projekt, und es passiert
vollständig im Browser.

## Warum überhaupt ein Modell

Ein d20 von oben ist ein Sechseck mit einer dreieckigen Fläche obenauf und fünf weiteren
Flächen, die von der Kamera weggeneigt sind, jede mit ihrer eigenen Zahl darauf. Ihn zu lesen
heißt, die eine Fläche zu finden, die frontal liegt, und nur die zu lesen. Dazu kommt, dass
Würfel sich in Farbe, Durchsichtigkeit, Druckfarbe und Oberfläche unterscheiden — und dass
eine 6 und eine 9 dasselbe Zeichen sind. Von Hand geschriebene Regeln lohnen sich dann nicht
mehr. Ein Klassifikator, der ein paar hundert *deiner* Würfel gesehen hat, ist einfacher und
besser zugleich.

## Sätze, Modelle, und was was ist

Zwei Wörter, die man leicht verwechselt — und aus dem Unterschied folgt alles andere.

**Ein Satz** ist eine Partie Würfel, unter einem Licht fotografiert. Er ist die Einheit, in
die *gesammelt* wird: Bilder auf der Platte mit einem Etikett pro Würfel. Benenn ihn nach den
Würfeln *und* dem Aufbau — „schwarze d20, Schreibtischlampe" —, denn ein Modell, das über zwei
verschiedene Aufbauten trainiert wurde, lernt deren Mittelwert und ist bei beiden schlechter.

**Ein Modell** ist das, was die Erkennung lädt und womit sie liest. Es wird aus **einem oder
mehreren Sätzen zugleich** trainiert und kennt genau die Flächen, die darin vorkamen, und
sonst nichts. Trainier aus einem Satz d6, und es liest d6; nimm einen Satz d20 dazu, und
dasselbe Modell liest beides.

Genau deshalb lohnt es sich, einen Satz zwischen Rechnern zu tragen: dein Freund besitzt die
d20, also sammelt er ein paar hundert Würfe auf seinem eigenen Turm, schickt dir die Datei,
und du trainierst ein Modell aus seinem und deinem Satz zusammen. **Export this set (.zip)**
und das Dateifeld daneben tun genau das — ein schlichtes Zip aus Bildern und Etiketten, das du
auch einfach entpacken und dir ansehen kannst.

Es ist immer nur ein Modell geladen. Unter **Models** wählst du welches; die Erkennung benutzt
dieses, und sie kann erkennen, was hineingegangen ist.

## Die Schleife

**Training → New set**, dann:

1. **Benenne den Satz nach dem Aufbau, nicht nur nach den Würfeln** — „schwarze d20,
   Schreibtischlampe". Ein Modell über zwei verschiedene Lichter lernt den Mittelwert beider
   und ist bei jedem schlechter.
2. **Würfeln und speichern.** DiceCore nimmt auf, findet die Würfel und trägt seine Vermutung
   schon ein. Ein Würfel, den es nicht lesen konnte, steht als `?` da.
3. **Korrigiere, was falsch ist, dann bestätige.** Nur bestätigte Würfel werden trainiert —
   auf unbestätigte Vermutungen zu trainieren bringt dem Modell seine eigenen Fehler bei.
4. Wiederholen. Häkchen bei **keep rolling**, dann wird alle paar Sekunden aufgenommen und du
   wirfst einfach weiter.

Sieh dir die Flächenzähler unter dem Satz an. „412 Beispiele" heißt nichts, wenn 400 davon ein
d20 mit einer 1 sind; die dünnen Flächen stehen dort, damit die nächste Handvoll Würfe auf sie
zielen kann.

## Drei Beispiele, von vorn bis hinten

**Normale Sechsseiter.** Vielleicht brauchst du gar kein Training — die klassische Erkennung
zählt Augen ohne jedes. Trainier nur, wenn deine Würfel ungewöhnlich sind: dunkel,
durchscheinend, seltsam bedruckt. Neuer Satz *„weiße d6, Küchenlampe"*, dann etwa sechzig
Würfel würfeln und bestätigen. Jeder Wurf mit dreien gibt dir drei, das sind also zwanzig
Würfe.

**Kniffel.** Dasselbe, und bei fünf Würfeln pro Wurf reichen zwölf Würfe für sechzig. Häkchen
bei *keep rolling*, werfen, hinsehen, korrigieren, wiederholen. Die Augen hat die Erkennung
meist schon richtig, also sind die meisten Würfe ein Blick und nichts zu tippen.

**Ein Rollenspielsatz.** Hier verdient das Training sein Geld: die klassische Erkennung kann
Ziffern gar nicht lesen, ein d20 ist also unlesbar, bis es ein Modell gibt. Stell unter
*Detection* ein, welche Würfel vorkommen dürfen, und würfle dann den d20 allein, bis jede
seiner zwanzig Flächen etwa zehnmal oben lag — zweihundert bestätigte Würfel, ein Abend. Den
d8, den d12 und den Rest im selben Satz oder in eigenen; in ein Modell können sie so oder so
alle zusammen.

Das Unangenehme am d20 ist, dass die Flächen zufällig kommen, die letzten paar brauchen also
Geduld. Die Zähler pro Fläche unter dem Satz zeigen, welche dünn sind; ziel mit den nächsten
Würfen darauf — oder nimm den Würfel in die Hand und leg ihn hin. Ein gelegter Würfel ist kein
fairer Wurf, aber ein völlig brauchbares Foto, und das Modell sieht ohnehin nur das Bild.

## Wie viel genug ist

| | Bestätigte Würfel | Was zu erwarten ist |
|---|---|---|
| Minimum zum Trainieren überhaupt | 60 | Es läuft; gut wird es nicht |
| Brauchbar | ~10 pro Fläche | Ein d20 braucht ~200, ein d6 ~60 |
| Bequem | ~25 pro Fläche | Ein d20 braucht ~500 |

Hundert Würfe mit vier Würfeln sind vierhundert Beispiele. Das ist ein Abend, und ungefähr der
Punkt, an dem ein d20-Modell anfängt, im guten Sinne langweilig zu werden.

Das mit Abstand Nützlichste, was du beim Sammeln variieren kannst: **wo in der Fläche die
Würfel landen und wie sie gedreht sind**. Variiere sonst nichts. Licht, Kamera und Fläche
sollten genau so bleiben, wie sie später im Betrieb sind.

## Trainieren

**Train** im Reiter Training. Fortschritt, Loss und Genauigkeit laufen live in die Seite; du
kannst den Browser schließen und wiederkommen. Es braucht PyTorch, läuft also auf einem PC —
der Reiter sagt es dir, wenn diese Maschine es nicht kann, und bietet einen **Knopf an, der es
installiert** (rund 2 GB; DiceCore muss danach neu gestartet werden, damit es greift).
Möglichkeiten:

- `~/.local/share/dicecore/datasets/<satz>` auf einen PC kopieren, dort DiceCore laufen
  lassen, trainieren, das Modellverzeichnis zurückkopieren.
- Oder das ganze DiceCore auf dem PC laufen lassen, den Pi mit `engine.mode=remote` darauf
  zeigen lassen, und nie etwas verschieben.

Aus dem Terminal ist es `dicecore train <satz-id> --epochs 30`.

Das Ergebnis ist ein Verzeichnis mit `model.onnx` und `model.json`. Drück **Use** daneben,
oder setz `engine.mode=model`.

## Was tatsächlich trainiert wird

Zwei Stufen. Das Finden der Würfel macht die klassische Segmentierung — das ist umsonst,
braucht keine Etiketten und ist nicht der schwere Teil. Das Modell *liest* nur einen
ausgeschnittenen Würfel:

- 64 × 64 Graustufen-Ausschnitt, quadratisch um die Würfelmitte, damit ein schräger Würfel nie
  gestreckt wird.
- Drei kleine Faltungsblöcke und ein Global Average Pool, ~200k Parameter. Es muss auf einem
  Pi laufen.
- Ausgabe: eine Klasse je `kind:value`, das im Satz vorkam, z. B. `d20:14`.

Die Genauigkeit kommt aus der Augmentierung: **volle 360°-Drehung**, dazu Verschiebung,
Skalierung und Helligkeit. Würfel landen in jeder Ausrichtung, das Modell muss also
drehinvariant sein — und das darf es sogar für 6 gegen 9 sein, denn Würfel klären das mit
einem Unterstrich, der sich mit der Ziffer mitdreht. Ohne Dreh-Augmentierung lernt das Modell
die Ausrichtung deines Turms.

Die Validierung wird pro Klasse getrennt, nicht zufällig: bei einem kleinen Satz kann eine
zufällige Teilung eine seltene Fläche ganz aus der Validierung herauslassen, und dann sagt die
Genauigkeitszahl nur etwas über die häufigen Flächen.

## Wenn es falsch liegt

Sammle weiter in denselben Satz — Korrekturen sind mehr wert als frische Vermutungen, denn sie
sind genau die Beispiele, die dem Modell fehlen. Dann neu trainieren. Achte auf **engine
agreement** beim Satz: das ist das ehrliche Maß dafür, wie die aktuelle Erkennung bei Würfeln
abschneidet, deren Antwort ihr noch niemand gesagt hat.
